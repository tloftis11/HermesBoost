import uuid
from datetime import date
from decimal import Decimal

import pytest_asyncio

from app.models.dataset import Dataset
from app.models.dataset_profile import DatasetProfile
from app.models.model import Model
from app.models.model_candidate import ModelCandidate
from app.models.model_run import ModelRun
from app.models.modeling_spec import ModelingSpec
from app.models.scheduled_score import ScheduledScore


@pytest_asyncio.fixture
async def confirmed_spec(db_session, default_org_id) -> ModelingSpec:
    dataset = Dataset(
        organization_id=default_org_id,
        name="types_sample.csv",
        storage_path=f"{default_org_id}/x/types_sample.csv",
        content_hash="testhash123",
        row_count=6,
        column_count=3,
        status="profiled",
    )
    db_session.add(dataset)
    await db_session.flush()

    db_session.add(
        DatasetProfile(
            organization_id=default_org_id,
            dataset_id=dataset.id,
            content_hash="testhash123",
            row_count=6,
            column_count=3,
            columns=[
                {"name": "row_id", "dtype": "id"},
                {"name": "amount", "dtype": "numeric"},
                {"name": "category", "dtype": "categorical"},
            ],
        )
    )
    spec = ModelingSpec(
        organization_id=default_org_id,
        dataset_id=dataset.id,
        status="confirmed",
        task_type="classification",
        target="category",
        candidate_features=["amount"],
    )
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)
    return spec


@pytest_asyncio.fixture
async def imbalanced_spec(db_session, default_org_id) -> ModelingSpec:
    dataset = Dataset(
        organization_id=default_org_id,
        name="rare_target.csv",
        storage_path=f"{default_org_id}/x/rare_target.csv",
        content_hash="rarehash",
        row_count=100,
        column_count=3,
        status="profiled",
    )
    db_session.add(dataset)
    await db_session.flush()

    db_session.add(
        DatasetProfile(
            organization_id=default_org_id,
            dataset_id=dataset.id,
            content_hash="rarehash",
            row_count=100,
            column_count=3,
            columns=[
                {"name": "row_id", "dtype": "id"},
                {"name": "amount", "dtype": "numeric"},
                {
                    "name": "had_event",
                    "dtype": "categorical",
                    "distinct_count": 2,
                    "top_values": [{"value": "False", "count": 85}, {"value": "True", "count": 15}],
                },
            ],
        )
    )
    spec = ModelingSpec(
        organization_id=default_org_id,
        dataset_id=dataset.id,
        status="confirmed",
        task_type="classification",
        target="had_event",
        candidate_features=["amount"],
    )
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)
    return spec


async def test_build_model_requires_imbalance_ack(client, imbalanced_spec):
    resp = await client.post(f"/api/v1/modeling-specs/{imbalanced_spec.id}/build")
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "imbalance_ack_required"
    assert detail["minority_rate"] == 0.15


async def test_build_model_proceeds_after_imbalance_ack(client, imbalanced_spec):
    ack_resp = await client.patch(
        f"/api/v1/modeling-specs/{imbalanced_spec.id}", json={"acknowledge_imbalance": True}
    )
    assert ack_resp.json()["acknowledged_imbalance"] is True

    resp = await client.post(f"/api/v1/modeling-specs/{imbalanced_spec.id}/build")
    assert resp.status_code == 202


async def test_build_model_skips_imbalance_gate_when_distinct_count_exceeds_cap(
    client, db_session, imbalanced_spec
):
    from sqlalchemy import select

    # Simulate a target with more distinct classes than top_values (capped
    # at 5) can reliably represent -- the pre-flight check can't be sure it
    # saw the true rarest class, so it should skip the gate rather than guess.
    result = await db_session.execute(
        select(DatasetProfile).where(DatasetProfile.dataset_id == imbalanced_spec.dataset_id)
    )
    profile = result.scalar_one()
    columns = profile.columns
    for c in columns:
        if c["name"] == "had_event":
            c["distinct_count"] = 6
    profile.columns = columns
    await db_session.commit()

    resp = await client.post(f"/api/v1/modeling-specs/{imbalanced_spec.id}/build")
    assert resp.status_code == 202


async def test_build_model_creates_training_row(client, confirmed_spec):
    resp = await client.post(f"/api/v1/modeling-specs/{confirmed_spec.id}/build")
    assert resp.status_code == 202
    body = resp.json()
    assert uuid.UUID(body["model_id"])
    assert uuid.UUID(body["model_run_id"])

    get_resp = await client.get(f"/api/v1/models/{body['model_id']}")
    assert get_resp.status_code == 200
    guided = get_resp.json()
    assert guided["status"] == "training"
    assert guided["active_candidate"] is None
    assert guided["latest_run"]["status"] == "running"


async def test_build_model_rejects_unsupported_task_type(client, confirmed_spec, db_session):
    confirmed_spec.task_type = "clustering"
    await db_session.commit()

    resp = await client.post(f"/api/v1/modeling-specs/{confirmed_spec.id}/build")
    assert resp.status_code == 400
    assert "not supported" in resp.json()["detail"]


async def test_build_model_reuses_existing_model_slot_on_retrain(client, confirmed_spec):
    first = await client.post(f"/api/v1/modeling-specs/{confirmed_spec.id}/build")
    second = await client.post(f"/api/v1/modeling-specs/{confirmed_spec.id}/build")

    assert first.json()["model_id"] == second.json()["model_id"]
    assert first.json()["model_run_id"] != second.json()["model_run_id"]


async def test_get_model_for_spec_404s_before_first_build(client, confirmed_spec):
    resp = await client.get(f"/api/v1/modeling-specs/{confirmed_spec.id}/models")
    assert resp.status_code == 404


async def test_unknown_model_404s(client):
    resp = await client.get(f"/api/v1/models/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest_asyncio.fixture
async def completed_model_with_leaderboard(db_session, default_org_id, confirmed_spec):
    model = Model(organization_id=default_org_id, modeling_spec_id=confirmed_spec.id, status="training")
    db_session.add(model)
    await db_session.flush()

    run = ModelRun(
        organization_id=default_org_id,
        model_id=model.id,
        run_type="train",
        status="completed",
        ml_task="classification",
        row_count_used=6,
        warnings=[],
        interpretation_summary="A plain-English summary.",
        interpretation_key_drivers=[{"feature": "amount", "plain_description": "matters", "relative_importance": 1.0}],
        interpretation_model="fake-model",
    )
    db_session.add(run)
    await db_session.flush()

    def _make_candidate(role: str, algorithm: str) -> ModelCandidate:
        return ModelCandidate(
            organization_id=default_org_id,
            model_run_id=run.id,
            role=role,
            algorithm=algorithm,
            ml_task="classification",
            feature_columns=["amount"],
            feature_dtypes={"amount": "numeric"},
            target_column="category",
            label_classes=["A", "B", "C"],
            metrics={"auc": 0.8, "precision": 0.7, "recall": 0.6, "accuracy": 0.75, "calibration_error": 0.05},
            feature_importance=[{"feature": "amount", "importance": 1.0}],
            hyperparams={"max_iter": 1000},
            train_time_seconds=Decimal("1.23"),
            storage_bucket="models",
            storage_path=f"{default_org_id}/{run.id}/{algorithm}.joblib",
        )

    recommended = _make_candidate("recommended", "flaml_lgbm")
    baselines = [
        _make_candidate("baseline", "logistic_regression"),
        _make_candidate("baseline", "random_forest"),
        _make_candidate("baseline", "xgboost"),
    ]
    db_session.add_all([recommended, *baselines])
    await db_session.flush()

    model.status = "ready"
    model.active_candidate_id = recommended.id
    await db_session.commit()
    await db_session.refresh(model)
    return model


async def test_get_model_guided_view(client, completed_model_with_leaderboard):
    resp = await client.get(f"/api/v1/models/{completed_model_with_leaderboard.id}")
    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] == "ready"
    assert body["active_candidate"]["algorithm"] == "flaml_lgbm"
    assert body["active_candidate"]["role"] == "recommended"
    assert body["latest_run"]["status"] == "completed"
    assert body["latest_run"]["interpretation_summary"] == "A plain-English summary."


async def test_get_model_leaderboard_recommended_first(client, completed_model_with_leaderboard):
    resp = await client.get(f"/api/v1/models/{completed_model_with_leaderboard.id}/leaderboard")
    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] == "ready"
    assert len(body["candidates"]) == 4
    assert body["candidates"][0]["role"] == "recommended"
    assert body["candidates"][0]["algorithm"] == "flaml_lgbm"
    remaining_roles = [c["role"] for c in body["candidates"][1:]]
    assert remaining_roles == ["baseline", "baseline", "baseline"]
    assert body["run"]["row_count_used"] == 6


async def test_get_model_for_spec_delegates_to_guided_view(client, confirmed_spec, completed_model_with_leaderboard):
    resp = await client.get(f"/api/v1/modeling-specs/{confirmed_spec.id}/models")
    assert resp.status_code == 200
    assert resp.json()["id"] == completed_model_with_leaderboard.id


async def test_list_models_empty(client):
    resp = await client.get("/api/v1/models")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_models_returns_shape_and_ordering(client, confirmed_spec, completed_model_with_leaderboard):
    resp = await client.get("/api/v1/models")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1

    item = items[0]
    assert item["id"] == completed_model_with_leaderboard.id
    assert item["dataset_name"] == "types_sample.csv"
    assert item["status"] == "ready"
    assert item["algorithm"] == "flaml_lgbm"
    assert item["ml_task"] == "classification"
    assert item["primary_metric_label"] == "AUC"
    assert item["primary_metric_value"] == 0.8


async def test_list_models_reflects_retrain_in_progress(client, confirmed_spec, completed_model_with_leaderboard):
    # Retraining reuses the spec's existing model slot; active_candidate_id
    # (and therefore the list's algorithm/metric) stays pointed at the
    # previous run's winner until the new run completes.
    build_resp = await client.post(f"/api/v1/modeling-specs/{confirmed_spec.id}/build")
    assert build_resp.status_code == 202

    resp = await client.get("/api/v1/models")
    items = resp.json()
    assert len(items) == 1
    assert items[0]["id"] == completed_model_with_leaderboard.id
    assert items[0]["status"] == "training"
    assert items[0]["algorithm"] == "flaml_lgbm"  # stale-but-valid, unchanged until the new run completes


async def test_score_model_requires_ready_status(client, confirmed_spec):
    build_resp = await client.post(f"/api/v1/modeling-specs/{confirmed_spec.id}/build")
    model_id = build_resp.json()["model_id"]

    resp = await client.post(f"/api/v1/models/{model_id}/score")
    assert resp.status_code == 400


async def test_score_model_creates_score_run(client, completed_model_with_leaderboard):
    resp = await client.post(f"/api/v1/models/{completed_model_with_leaderboard.id}/score")
    assert resp.status_code == 202
    body = resp.json()
    assert uuid.UUID(body["model_run_id"])

    scores_resp = await client.get(f"/api/v1/models/{completed_model_with_leaderboard.id}/scores")
    assert scores_resp.status_code == 200
    scores = scores_resp.json()
    assert scores["run"]["id"] == body["model_run_id"]
    assert scores["run"]["status"] == "running"  # score_model.delay is stubbed to a no-op in tests
    assert scores["rows"] == []


async def test_get_scores_empty_before_any_score_run(client, completed_model_with_leaderboard):
    resp = await client.get(f"/api/v1/models/{completed_model_with_leaderboard.id}/scores")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run"] is None
    assert body["rows"] == []


async def test_get_scores_returns_rows_from_latest_run(
    client, db_session, default_org_id, completed_model_with_leaderboard
):
    model = completed_model_with_leaderboard
    run = ModelRun(
        organization_id=default_org_id, model_id=model.id, run_type="score",
        status="completed", row_count_used=2,
    )
    db_session.add(run)
    await db_session.flush()
    db_session.add_all([
        ScheduledScore(
            organization_id=default_org_id, model_id=model.id, model_run_id=run.id,
            model_candidate_id=model.active_candidate_id, entity_id="1",
            score_date=date.today(), predicted_label="A", predicted_probability=0.9,
        ),
        ScheduledScore(
            organization_id=default_org_id, model_id=model.id, model_run_id=run.id,
            model_candidate_id=model.active_candidate_id, entity_id="2",
            score_date=date.today(), predicted_label="B", predicted_probability=0.6,
        ),
    ])
    await db_session.commit()

    resp = await client.get(f"/api/v1/models/{model.id}/scores")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_row_count"] == 2
    assert len(body["rows"]) == 2
    assert {r["entity_id"] for r in body["rows"]} == {"1", "2"}


async def test_promote_candidate_switches_active(client, db_session, completed_model_with_leaderboard):
    from sqlalchemy import select

    model = completed_model_with_leaderboard
    result = await db_session.execute(
        select(ModelCandidate).where(
            ModelCandidate.model_run_id.in_(
                select(ModelRun.id).where(ModelRun.model_id == model.id)
            ),
            ModelCandidate.role == "baseline",
        )
    )
    baseline = result.scalars().first()
    assert baseline.id != model.active_candidate_id

    resp = await client.post(f"/api/v1/models/{model.id}/promote", json={"candidate_id": baseline.id})
    assert resp.status_code == 200
    assert resp.json()["active_candidate"]["id"] == baseline.id

    get_resp = await client.get(f"/api/v1/models/{model.id}")
    assert get_resp.json()["active_candidate"]["id"] == baseline.id


async def test_promote_candidate_rejects_foreign_candidate(client, completed_model_with_leaderboard, confirmed_spec):
    resp = await client.post(
        f"/api/v1/models/{completed_model_with_leaderboard.id}/promote",
        json={"candidate_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


@pytest_asyncio.fixture
async def multi_day_scores(db_session, default_org_id, completed_model_with_leaderboard):
    """Two score runs on different dates, each scoring two entities, so
    date/entity/range filtering has something real to distinguish."""
    from datetime import datetime, timedelta, timezone

    model = completed_model_with_leaderboard
    today = date.today()
    yesterday = today - timedelta(days=1)

    # Explicit, distinct started_at values -- both rows would otherwise be
    # created in the same transaction and tie on server_default=func.now(),
    # making "latest run" ambiguous (the same class of issue the leaderboard
    # sort already works around by sorting in Python instead of SQL).
    run_yesterday = ModelRun(
        organization_id=default_org_id, model_id=model.id, run_type="score",
        status="completed", row_count_used=2,
        started_at=datetime.combine(yesterday, datetime.min.time(), tzinfo=timezone.utc),
    )
    run_today = ModelRun(
        organization_id=default_org_id, model_id=model.id, run_type="score",
        status="completed", row_count_used=2,
        started_at=datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc),
    )
    db_session.add_all([run_yesterday, run_today])
    await db_session.flush()

    db_session.add_all([
        ScheduledScore(
            organization_id=default_org_id, model_id=model.id, model_run_id=run_yesterday.id,
            model_candidate_id=model.active_candidate_id, entity_id="1",
            score_date=yesterday, predicted_label="A", predicted_probability=0.9,
        ),
        ScheduledScore(
            organization_id=default_org_id, model_id=model.id, model_run_id=run_yesterday.id,
            model_candidate_id=model.active_candidate_id, entity_id="2",
            score_date=yesterday, predicted_label="B", predicted_probability=0.5,
        ),
        ScheduledScore(
            organization_id=default_org_id, model_id=model.id, model_run_id=run_today.id,
            model_candidate_id=model.active_candidate_id, entity_id="1",
            score_date=today, predicted_label="A", predicted_probability=0.95,
        ),
        ScheduledScore(
            organization_id=default_org_id, model_id=model.id, model_run_id=run_today.id,
            model_candidate_id=model.active_candidate_id, entity_id="2",
            score_date=today, predicted_label="B", predicted_probability=0.6,
        ),
    ])
    await db_session.commit()
    return model, yesterday, today


async def test_get_scores_default_still_returns_only_latest_run(client, multi_day_scores):
    model, yesterday, today = multi_day_scores
    resp = await client.get(f"/api/v1/models/{model.id}/scores")
    body = resp.json()
    assert len(body["rows"]) == 2
    assert all(r["score_date"] == today.isoformat() for r in body["rows"])
    assert body["run"] is not None  # single-run default still populates run metadata


async def test_get_scores_exact_date_filter(client, multi_day_scores):
    model, yesterday, today = multi_day_scores
    resp = await client.get(f"/api/v1/models/{model.id}/scores", params={"score_date": yesterday.isoformat()})
    body = resp.json()
    assert len(body["rows"]) == 2
    assert all(r["score_date"] == yesterday.isoformat() for r in body["rows"])
    assert body["run"] is None  # filtered query -- no single-run metadata


async def test_get_scores_date_range_filter(client, multi_day_scores):
    model, yesterday, today = multi_day_scores
    resp = await client.get(
        f"/api/v1/models/{model.id}/scores",
        params={"score_date_from": yesterday.isoformat(), "score_date_to": today.isoformat()},
    )
    body = resp.json()
    assert len(body["rows"]) == 4
    assert body["total_row_count"] == 4


async def test_get_scores_entity_filter_spans_dates(client, multi_day_scores):
    model, yesterday, today = multi_day_scores
    resp = await client.get(f"/api/v1/models/{model.id}/scores", params={"entity_id": "1"})
    body = resp.json()
    assert len(body["rows"]) == 2
    assert all(r["entity_id"] == "1" for r in body["rows"])
    assert {r["score_date"] for r in body["rows"]} == {yesterday.isoformat(), today.isoformat()}


async def test_get_scores_csv_format(client, multi_day_scores):
    model, yesterday, today = multi_day_scores
    resp = await client.get(
        f"/api/v1/models/{model.id}/scores",
        params={"score_date_from": yesterday.isoformat(), "score_date_to": today.isoformat(), "format": "csv"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    lines = resp.text.strip().splitlines()
    assert lines[0] == "entity_id,score_date,predicted_value,predicted_label,predicted_probability"
    assert len(lines) == 5  # header + 4 rows


async def test_get_scores_pagination_limit(client, multi_day_scores):
    model, yesterday, today = multi_day_scores
    resp = await client.get(
        f"/api/v1/models/{model.id}/scores",
        params={"score_date_from": yesterday.isoformat(), "score_date_to": today.isoformat(), "limit": 1},
    )
    body = resp.json()
    assert len(body["rows"]) == 1
    assert body["total_row_count"] == 4  # total matching the filter, not just this page


async def test_get_scores_with_valid_api_key(client, multi_day_scores):
    model, _yesterday, _today = multi_day_scores
    created = (await client.post("/api/v1/api-keys", json={"name": "external"})).json()

    resp = await client.get(f"/api/v1/models/{model.id}/scores", headers={"x-api-key": created["raw_key"]})
    assert resp.status_code == 200
    assert len(resp.json()["rows"]) == 2


async def test_get_scores_with_invalid_api_key_401s(client, multi_day_scores):
    model, _yesterday, _today = multi_day_scores
    resp = await client.get(f"/api/v1/models/{model.id}/scores", headers={"x-api-key": "bogus"})
    assert resp.status_code == 401
