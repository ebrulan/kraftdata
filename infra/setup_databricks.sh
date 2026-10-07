#!/usr/bin/env bash
# Creates an Azure Databricks workspace and lets Unity Catalog read the raw container.
# Run after infra/setup.sh.
#
# Choices:
#   - Premium SKU: required for Unity Catalog. The "trial" SKU (free DBUs) is not
#     allowed on Azure Free Trial subscriptions.
#   - --enable-no-public-ip false: with secure cluster connectivity on the default
#     managed VNet, Azure adds a NAT gateway that is billed every hour, even when
#     no cluster runs. Public IPs on cluster nodes only cost while a cluster is up.
#   - The workspace itself costs nothing; compute is billed only while running.
#
# Teardown: deleting the resource group also deletes the workspace and its managed
# resource group:
#   az group delete --name "$RESOURCE_GROUP" --yes --no-wait
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-kraftdata}"
LOCATION="${LOCATION:-norwayeast}"
WORKSPACE="${WORKSPACE:-dbw-kraftdata}"
MANAGED_RG="${MANAGED_RG:-$RESOURCE_GROUP-dbw-managed}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:?Set STORAGE_ACCOUNT to the account from setup.sh}"
CONTAINER="${CONTAINER:-raw}"
PROFILE="${DATABRICKS_CONFIG_PROFILE:-kraftdata}"

az extension add --name databricks --only-show-errors

az databricks workspace create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WORKSPACE" \
  --location "$LOCATION" \
  --sku premium \
  --compute-mode Hybrid \
  --enable-no-public-ip false \
  --managed-resource-group "$MANAGED_RG" \
  --tags project=kraftdata \
  --output none

HOST="https://$(az databricks workspace show \
  --resource-group "$RESOURCE_GROUP" --name "$WORKSPACE" --query workspaceUrl -o tsv)"

# New workspaces are automatically attached to a Unity Catalog metastore with an
# access connector (a managed identity). Give that identity access to the lake.
CONNECTOR_PRINCIPAL=$(az databricks access-connector show \
  --resource-group "$MANAGED_RG" --name unity-catalog-access-connector \
  --query identity.principalId -o tsv)
STORAGE_ID=$(az storage account show \
  --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" --query id -o tsv)
az role assignment create \
  --assignee-object-id "$CONNECTOR_PRINCIPAL" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" \
  --scope "$STORAGE_ID" \
  --output none

# Databricks CLI profile that reuses the Azure CLI login (no personal access token).
if ! grep -q "^\[$PROFILE\]" ~/.databrickscfg 2>/dev/null; then
  printf "\n[%s]\nhost = %s\nauth_type = azure-cli\n" "$PROFILE" "$HOST" >> ~/.databrickscfg
  chmod 600 ~/.databrickscfg
fi
export DATABRICKS_CONFIG_PROFILE="$PROFILE"

# The workspace's default storage credential may only reach the workspace's own
# storage, so create a dedicated credential on the same access connector.
CONNECTOR_ID=$(az databricks access-connector show \
  --resource-group "$MANAGED_RG" --name unity-catalog-access-connector --query id -o tsv)
databricks storage-credentials create --json "{
  \"name\": \"kraftdata_adls\",
  \"azure_managed_identity\": {\"access_connector_id\": \"$CONNECTOR_ID\"}
}"

echo "Waiting for role assignment to propagate..."
sleep 60
# File events (used by Auto Loader notifications) need extra Event Grid roles; we don't use them.
databricks external-locations create kraftdata_raw \
  "abfss://$CONTAINER@$STORAGE_ACCOUNT.dfs.core.windows.net/" kraftdata_adls \
  --comment "Raw landing zone for kraftdata API data"
databricks external-locations update kraftdata_raw --json '{"enable_file_events": false}'

databricks storage-credentials validate \
  --json '{"storage_credential_name":"kraftdata_adls","external_location_name":"kraftdata_raw"}'

# Schemas, the raw volume and a secret scope for the daily job.
databricks schemas create landing dbw_kraftdata
databricks schemas create bronze dbw_kraftdata
databricks volumes create dbw_kraftdata landing raw EXTERNAL \
  --storage-location "abfss://$CONTAINER@$STORAGE_ACCOUNT.dfs.core.windows.net/"
databricks secrets create-scope kraftdata
echo "Add the ENTSO-E key with: databricks secrets put-secret kraftdata entsoe_api_key"

echo "Workspace: $HOST"
