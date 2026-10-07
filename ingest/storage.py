"""Writes files to the raw zone, either in ADLS Gen2 or on a local/mounted path.

Paths are deterministic (source + date), and every write overwrites the whole file.
Re-running ingestion for a date therefore replaces that date's data instead of
appending duplicates, which is what makes the pipeline idempotent.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path


class RawStore:
    """Raw zone backed by ADLS Gen2 (`account` set) or a local directory (e.g. a UC volume)."""

    def __init__(self, account: str | None = None, container: str = "raw", local_root: str = ""):
        if not account and not local_root:
            raise ValueError("Set either an ADLS account or a local root directory")
        self.local_root = Path(local_root) if local_root else None
        self._fs = None
        if account and not local_root:
            from azure.identity import DefaultAzureCredential
            from azure.storage.filedatalake import DataLakeServiceClient

            service = DataLakeServiceClient(
                account_url=f"https://{account}.dfs.core.windows.net",
                credential=DefaultAzureCredential(),
            )
            self._fs = service.get_file_system_client(container)

    def write_jsonl(self, path: str, rows: Iterable[dict]) -> int:
        lines = [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows]
        data = ("\n".join(lines) + "\n").encode("utf-8") if lines else b""
        if self.local_root is not None:
            target = self.local_root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        else:
            self._fs.get_file_client(path).upload_data(data, overwrite=True)
        return len(lines)
