"""The two custom tools behind the data-acquisition assistant --
everything Anthropic's hosted web_search/web_fetch tools can't do, since
they extract page content, not binary spreadsheet data.

Deliberately CSV/Excel only for v1 -- no PDF parsing, no multi-sheet Excel
selection (only the first/default sheet is read). Both tools always
return a plain string and never raise -- a failed download or an
unparseable file is reported back to Claude as an error message, not a
crashed turn, matching this codebase's existing tool-result convention
(see app/tasks/score_model.py's is_error handling for the same idea)."""

import io
import json
import uuid

import httpx
import pandas as pd
from anthropic import beta_async_tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset
from app.services.hashing import sha256_hex
from app.services.storage import get_storage_backend

MAX_DOWNLOAD_BYTES = 15 * 1024 * 1024  # 15MB
DOWNLOAD_TIMEOUT_SECONDS = 20.0
PREVIEW_ROWS = 10
BUCKET = "datasets"


async def _download(url: str) -> bytes:
    async with httpx.AsyncClient(follow_redirects=True, timeout=DOWNLOAD_TIMEOUT_SECONDS) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            chunks = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise ValueError(f"File exceeds the {MAX_DOWNLOAD_BYTES // (1024 * 1024)}MB size limit")
                chunks.append(chunk)
            return b"".join(chunks)


def _is_excel(url: str) -> bool:
    lowered = url.lower().split("?")[0]
    return lowered.endswith(".xlsx") or lowered.endswith(".xls")


def _parse_to_dataframe(url: str, content: bytes) -> pd.DataFrame:
    if _is_excel(url):
        return pd.read_excel(io.BytesIO(content), engine="openpyxl")
    return pd.read_csv(io.BytesIO(content))


def build_tools(db: AsyncSession, organization_id: str) -> tuple[list, list[str]]:
    """Returns (tools, staged_dataset_ids) -- the second is a list the
    caller should inspect *after* the tool loop finishes; stage_dataset
    appends to it as a side effect, since the tool's own return value is
    just a text string as far as the model is concerned, but the router
    needs the real dataset ids to surface confirm/discard actions."""
    staged_dataset_ids: list[str] = []

    @beta_async_tool
    async def preview_data_file(url: str) -> str:
        """Download a candidate data file and preview its structure (columns,
        row count, and a few sample rows). Call this before staging anything,
        to confirm it's actually tabular data with the columns you expect.
        Only CSV and Excel (.xlsx) files are supported -- if the URL points
        at a webpage rather than a downloadable file, use web_fetch instead
        to find the actual file link first. For an Excel file with multiple
        sheets, only the first sheet is read."""
        try:
            content = await _download(url)
            df = _parse_to_dataframe(url, content)
        except Exception as exc:  # noqa: BLE001 -- reported to Claude, not raised
            return f"Could not preview this file: {exc}"

        return json.dumps(
            {
                "columns": list(df.columns.astype(str)),
                "row_count": len(df),
                "sample_rows": json.loads(df.head(PREVIEW_ROWS).to_json(orient="records")),
            }
        )

    @beta_async_tool
    async def stage_dataset(url: str, name: str) -> str:
        """Save a candidate data file as a staged dataset for the user to
        review. This does NOT create a usable dataset yet -- the user must
        confirm it in the app before it can be profiled or used in a model.
        Only call this after preview_data_file has confirmed the file looks
        right. `name` should be a short, descriptive filename ending in .csv
        (e.g. "tx_county_vaccination_coverage.csv")."""
        try:
            content = await _download(url)
            if _is_excel(url):
                df = _parse_to_dataframe(url, content)
                csv_bytes = df.to_csv(index=False).encode("utf-8")
            else:
                csv_bytes = content
        except Exception as exc:  # noqa: BLE001
            return f"Could not stage this file: {exc}"

        if not name.lower().endswith(".csv"):
            name = f"{name}.csv"

        dataset_id = str(uuid.uuid4())
        storage_path = f"{organization_id}/{dataset_id}/{name}"
        get_storage_backend().upload(BUCKET, storage_path, csv_bytes)

        dataset = Dataset(
            id=dataset_id,
            organization_id=organization_id,
            name=name,
            storage_bucket=BUCKET,
            storage_path=storage_path,
            content_hash=sha256_hex(csv_bytes),
            size_bytes=len(csv_bytes),
            status="uploaded",
            pending_confirmation=True,
            source_url=url,
        )
        db.add(dataset)
        await db.commit()
        staged_dataset_ids.append(dataset_id)

        return json.dumps(
            {
                "dataset_id": dataset_id,
                "name": name,
                "message": "Staged for the user's review -- not yet a usable dataset until they confirm it.",
            }
        )

    tools = [
        {"type": "web_search_20260209", "name": "web_search"},
        {"type": "web_fetch_20260209", "name": "web_fetch"},
        preview_data_file,
        stage_dataset,
    ]
    return tools, staged_dataset_ids
