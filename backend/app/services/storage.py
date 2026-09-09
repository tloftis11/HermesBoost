"""Blob storage abstraction: Supabase Storage in production, a local-disk
backend for offline dev/tests (STORAGE_BACKEND=local)."""

from pathlib import Path
from typing import Protocol

from app.config import settings


class StorageBackend(Protocol):
    def upload(self, bucket: str, path: str, data: bytes) -> None: ...
    def download(self, bucket: str, path: str) -> bytes: ...


class LocalStorageBackend:
    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir or settings.LOCAL_STORAGE_DIR)

    def _resolve(self, bucket: str, path: str) -> Path:
        return self.base_dir / bucket / path

    def upload(self, bucket: str, path: str, data: bytes) -> None:
        full_path = self._resolve(bucket, path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(data)

    def download(self, bucket: str, path: str) -> bytes:
        return self._resolve(bucket, path).read_bytes()


class SupabaseStorageBackend:
    def __init__(self):
        from supabase import Client, create_client

        self._client: Client = create_client(
            settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY
        )

    def upload(self, bucket: str, path: str, data: bytes) -> None:
        self._client.storage.from_(bucket).upload(
            path, data, file_options={"upsert": "true"}
        )

    def download(self, bucket: str, path: str) -> bytes:
        return self._client.storage.from_(bucket).download(path)


_backend: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    global _backend
    if _backend is None:
        _backend = (
            LocalStorageBackend()
            if settings.STORAGE_BACKEND == "local"
            else SupabaseStorageBackend()
        )
    return _backend


def set_storage_backend_for_tests(backend: StorageBackend) -> None:
    """Test-only hook: force a specific backend (e.g. a LocalStorageBackend
    pointed at a pytest tmp_path), bypassing the STORAGE_BACKEND env var
    entirely. Tests must never depend on -- or leak into -- whatever a
    developer's local .env happens to be pointed at (this is how two stray
    files ended up in the real Supabase bucket during dev)."""
    global _backend
    _backend = backend
