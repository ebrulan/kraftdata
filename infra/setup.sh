#!/usr/bin/env bash
# Creates the Azure resources for kraftdata:
#   - a resource group
#   - a StorageV2 account with hierarchical namespace (= ADLS Gen2)
#   - a "raw" container (file system) for landing raw API data
#
# Cost: Standard_LRS storage with a few GB of data costs well under 1 USD per month.
# Teardown (deletes everything created here):
#   az group delete --name "$RESOURCE_GROUP" --yes --no-wait
#
# Usage: az login first, then
#   STORAGE_ACCOUNT=kraftdata<suffix> ./infra/setup.sh
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-kraftdata}"
LOCATION="${LOCATION:-norwayeast}"
# Storage account names are global: 3-24 lowercase letters and digits.
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:?Set STORAGE_ACCOUNT, e.g. kraftdata<initials><digits>}"
CONTAINER="${CONTAINER:-raw}"

echo "Subscription: $(az account show --query name -o tsv)"

az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --tags project=kraftdata \
  --output none

az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --hns true \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false \
  --tags project=kraftdata \
  --output none

# Grant the signed-in user data-plane access, so we can use Entra ID
# (--auth-mode login) instead of storage account keys.
STORAGE_ID=$(az storage account show \
  --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" --query id -o tsv)
USER_ID=$(az ad signed-in-user show --query id -o tsv)
az role assignment create \
  --assignee-object-id "$USER_ID" \
  --assignee-principal-type User \
  --role "Storage Blob Data Contributor" \
  --scope "$STORAGE_ID" \
  --output none

# Role assignments can take a minute to propagate.
for attempt in 1 2 3 4 5 6; do
  if az storage fs create \
       --name "$CONTAINER" \
       --account-name "$STORAGE_ACCOUNT" \
       --auth-mode login \
       --output none 2>/dev/null; then
    break
  fi
  echo "Waiting for role assignment to propagate (attempt $attempt)..."
  sleep 20
done

az storage fs show --name "$CONTAINER" --account-name "$STORAGE_ACCOUNT" \
  --auth-mode login --query name -o tsv
echo "Done: abfss://$CONTAINER@$STORAGE_ACCOUNT.dfs.core.windows.net/"
