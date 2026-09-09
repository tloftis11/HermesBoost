import json

import pytest_asyncio

import app.services.llm.data_acquisition_tools as tools_module
from app.models.dataset import Dataset
from app.services.llm.data_acquisition_tools import _is_excel, build_tools
from app.services.storage import LocalStorageBackend, set_storage_backend_for_tests


@pytest_asyncio.fixture
async def storage(tmp_path):
    backend = LocalStorageBackend(base_dir=str(tmp_path))
    set_storage_backend_for_tests(backend)
    return backend


def test_is_excel_detects_extension():
    assert _is_excel("https://example.com/data.xlsx") is True
    assert _is_excel("https://example.com/data.xls?query=1") is True
    assert _is_excel("https://example.com/data.csv") is False


async def test_preview_data_file_returns_columns_and_sample(monkeypatch, db_session, default_org_id, storage):
    csv_bytes = b"a,b\n1,2\n3,4\n5,6\n"

    async def fake_download(url: str) -> bytes:
        return csv_bytes

    monkeypatch.setattr(tools_module, "_download", fake_download)

    tools, staged = build_tools(db_session, default_org_id)
    preview_tool = next(t for t in tools if not isinstance(t, dict) and t.name == "preview_data_file")

    result = await preview_tool.func(url="https://example.com/data.csv")
    parsed = json.loads(result)
    assert parsed["columns"] == ["a", "b"]
    assert parsed["row_count"] == 3
    assert parsed["sample_rows"][0] == {"a": 1, "b": 2}


async def test_preview_data_file_reports_error_without_raising(monkeypatch, db_session, default_org_id, storage):
    async def fake_download(url: str) -> bytes:
        raise ValueError("boom")

    monkeypatch.setattr(tools_module, "_download", fake_download)

    tools, staged = build_tools(db_session, default_org_id)
    preview_tool = next(t for t in tools if not isinstance(t, dict) and t.name == "preview_data_file")

    result = await preview_tool.func(url="https://example.com/bad.csv")
    assert "Could not preview" in result
    assert "boom" in result


async def test_stage_dataset_creates_pending_confirmation_row(monkeypatch, db_session, default_org_id, storage):
    csv_bytes = b"county,cases\nGaines,414\nEl Paso,61\n"

    async def fake_download(url: str) -> bytes:
        return csv_bytes

    monkeypatch.setattr(tools_module, "_download", fake_download)

    tools, staged = build_tools(db_session, default_org_id)
    stage_tool = next(t for t in tools if not isinstance(t, dict) and t.name == "stage_dataset")

    result = await stage_tool.func(url="https://example.com/cases.csv", name="tx_cases")
    parsed = json.loads(result)
    assert "dataset_id" in parsed
    assert staged == [parsed["dataset_id"]]

    dataset = await db_session.get(Dataset, parsed["dataset_id"])
    assert dataset is not None
    assert dataset.pending_confirmation is True
    assert dataset.source_url == "https://example.com/cases.csv"
    assert dataset.name == "tx_cases.csv"
    assert dataset.status == "uploaded"

    downloaded = storage.download(dataset.storage_bucket, dataset.storage_path)
    assert downloaded == csv_bytes


async def test_stage_dataset_converts_excel_to_csv(monkeypatch, db_session, default_org_id, storage):
    import io

    import pandas as pd

    df = pd.DataFrame({"county": ["Gaines"], "cases": [414]})
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    xlsx_bytes = buf.getvalue()

    async def fake_download(url: str) -> bytes:
        return xlsx_bytes

    monkeypatch.setattr(tools_module, "_download", fake_download)

    tools, staged = build_tools(db_session, default_org_id)
    stage_tool = next(t for t in tools if not isinstance(t, dict) and t.name == "stage_dataset")

    result = await stage_tool.func(url="https://example.com/cases.xlsx", name="tx_cases")
    parsed = json.loads(result)

    dataset = await db_session.get(Dataset, parsed["dataset_id"])
    downloaded = storage.download(dataset.storage_bucket, dataset.storage_path)
    assert downloaded.decode().splitlines()[0] == "county,cases"
