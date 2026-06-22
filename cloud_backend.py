from __future__ import annotations

from typing import Any, Iterable

from supabase import Client, create_client

from config import CloudSettings


class CloudConfigurationError(RuntimeError):
    pass


class CloudDB:
    def __init__(self, settings: CloudSettings):
        if not settings.supabase_url or not settings.supabase_key:
            raise CloudConfigurationError(
                "SUPABASE_URL and SUPABASE_KEY are required in Streamlit secrets."
            )
        self.settings = settings
        self.client: Client = create_client(settings.supabase_url, settings.supabase_key)

    @staticmethod
    def _data(response: Any) -> list[dict[str, Any]]:
        data = getattr(response, "data", None)
        if data is None and isinstance(response, dict):
            data = response.get("data")
        if data is None:
            return []
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    def select(self, table: str, *, columns: str = "*", filters: dict[str, Any] | None = None,
               in_filters: dict[str, Iterable[Any]] | None = None, order: str | None = None,
               desc: bool = False, limit: int | None = None) -> list[dict[str, Any]]:
        query = self.client.table(table).select(columns)
        for key, value in (filters or {}).items():
            query = query.is_(key, "null") if value is None else query.eq(key, value)
        for key, values in (in_filters or {}).items():
            query = query.in_(key, list(values))
        if order:
            query = query.order(order, desc=desc)
        if limit:
            query = query.limit(limit)
        return self._data(query.execute())

    def select_one(self, table: str, *, columns: str = "*", filters: dict[str, Any] | None = None,
                   order: str | None = None, desc: bool = False) -> dict[str, Any] | None:
        rows = self.select(table, columns=columns, filters=filters, order=order, desc=desc, limit=1)
        return rows[0] if rows else None

    def insert(self, table: str, payload: dict[str, Any]) -> dict[str, Any]:
        rows = self._data(self.client.table(table).insert(payload).execute())
        if not rows:
            raise RuntimeError(f"Insert into {table} did not return a row")
        return rows[0]

    def update(self, table: str, payload: dict[str, Any], *, filters: dict[str, Any]) -> list[dict[str, Any]]:
        query = self.client.table(table).update(payload)
        for key, value in filters.items():
            query = query.eq(key, value)
        return self._data(query.execute())

    def upsert(self, table: str, payload: dict[str, Any], *, on_conflict: str | None = None) -> list[dict[str, Any]]:
        query = self.client.table(table).upsert(payload, on_conflict=on_conflict)
        return self._data(query.execute())

    def rpc(self, function_name: str, params: dict[str, Any] | None = None) -> Any:
        return getattr(self.client.rpc(function_name, params or {}).execute(), "data", None)

    def upload_bytes(self, bucket_name: str, path: str, content: bytes, mime_type: str, *, upsert: bool = False) -> str:
        bucket = self.client.storage.from_(bucket_name)
        options = {"content-type": mime_type, "upsert": "true" if upsert else "false"}
        if upsert:
            try:
                bucket.update(path=path, file=content, file_options=options)
            except Exception:
                bucket.upload(path=path, file=content, file_options=options)
        else:
            bucket.upload(path=path, file=content, file_options=options)
        return path

    def download_bytes(self, bucket_name: str, path: str) -> bytes:
        return bytes(self.client.storage.from_(bucket_name).download(path))

    def signed_url(self, bucket_name: str, path: str, expires_in: int = 3600) -> str | None:
        if not path:
            return None
        try:
            result = self.client.storage.from_(bucket_name).create_signed_url(path, expires_in)
        except Exception:
            return None
        if isinstance(result, dict):
            data = result.get("data", result)
            if isinstance(data, dict):
                return data.get("signedURL") or data.get("signedUrl") or data.get("signed_url")
        data = getattr(result, "data", None)
        if isinstance(data, dict):
            return data.get("signedURL") or data.get("signedUrl") or data.get("signed_url")
        return getattr(result, "signedURL", None) or getattr(result, "signed_url", None)
