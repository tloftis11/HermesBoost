import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getLeaderboard } from "../api/models";
import { getModelingSpec } from "../api/modelingSpecs";
import { HyperparamsPanel } from "../components/HyperparamsPanel";
import { KeyDriversList } from "../components/KeyDriversList";
import { Leaderboard, formatAlgorithm } from "../components/Leaderboard";
import { RunMetadataFooter } from "../components/RunMetadataFooter";
import { Sidebar } from "../components/Sidebar";
import { useModelRun } from "../hooks/useModelRun";
import type { Leaderboard as LeaderboardData, ModelGuided, ModelingSpec } from "../types";

type ViewMode = "guided" | "advanced";

export function ModelResultsPage() {
  const { modelId } = useParams<{ modelId: string }>();
  const { model, loading } = useModelRun(modelId ?? null);

  const [spec, setSpec] = useState<ModelingSpec | null>(null);
  const [view, setView] = useState<ViewMode>("guided");
  const [leaderboard, setLeaderboard] = useState<LeaderboardData | null>(null);
  const [leaderboardError, setLeaderboardError] = useState<string | null>(null);

  useEffect(() => {
    if (!model) return;
    getModelingSpec(model.modeling_spec_id)
      .then((detail) => setSpec(detail.spec))
      .catch(() => {});
  }, [model?.modeling_spec_id]);

  useEffect(() => {
    if (!modelId || !model || model.status === "training") return;
    getLeaderboard(modelId)
      .then(setLeaderboard)
      .catch((err) => setLeaderboardError(err instanceof Error ? err.message : "Could not load leaderboard"));
  }, [modelId, model?.status]);

  const breadcrumbLabel = spec?.task_description || "Model results";

  return (
    <div className="shell">
      <Sidebar activeItem="models" />
      <div className="main">
        <div className="topbar">
          <div className="breadcrumb">
            <Link to="/models">Models</Link> / <b>{breadcrumbLabel}</b>
          </div>
          {model?.status === "ready" && (
            <div className="topbar-right">
              <div className="segmented">
                <button
                  type="button"
                  className={`seg-btn${view === "guided" ? " active" : ""}`}
                  onClick={() => setView("guided")}
                >
                  Guided
                </button>
                <button
                  type="button"
                  className={`seg-btn${view === "advanced" ? " active" : ""}`}
                  onClick={() => setView("advanced")}
                >
                  Advanced
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="content">
          {loading && !model ? (
            <div className="empty-state">Loading model…</div>
          ) : !model ? (
            <div className="card" style={{ borderColor: "var(--bad)", color: "var(--bad)" }}>
              Model not found.
            </div>
          ) : model.status === "training" ? (
            <div className="card">
              <h3>Training in progress</h3>
              <p className="spec-caption">
                Fitting a leaderboard of candidate models -- this usually takes a minute or two. This page
                updates automatically.
              </p>
            </div>
          ) : model.status === "error" ? (
            <div className="card" style={{ borderColor: "var(--bad)", color: "var(--bad)" }}>
              <h3>Training failed</h3>
              <p>{model.error_message ?? "An unknown error occurred while building this model."}</p>
            </div>
          ) : view === "guided" ? (
            <GuidedView model={model} onSeeFullMetrics={() => setView("advanced")} />
          ) : (
            <AdvancedView leaderboard={leaderboard} leaderboardError={leaderboardError} />
          )}
        </div>
      </div>
    </div>
  );
}

function GuidedView({
  model,
  onSeeFullMetrics,
}: {
  model: ModelGuided;
  onSeeFullMetrics: () => void;
}) {
  const candidate = model.active_candidate;
  const run = model.latest_run;
  const isClassification = candidate?.ml_task === "classification";
  const primaryMetricValue = candidate
    ? isClassification
      ? candidate.metrics.auc
      : candidate.metrics.r2
    : undefined;
  const primaryMetricLabel = isClassification ? "Accuracy (AUC)" : "Fit (R²)";

  return (
    <>
      <div className="status-row">
        <span className="pill good">Ready</span>
        {run && <span>Trained {new Date(run.completed_at ?? run.started_at).toLocaleDateString()}</span>}
      </div>

      <div className="card summary-card">
        <h3>In plain terms</h3>
        <p>{run?.interpretation_summary ?? "No interpretation is available for this run yet."}</p>
      </div>

      {candidate && (
        <div className="rec-row">
          <div className="card rec-card">
            <div className="rec-badge">★</div>
            <div>
              <div className="rec-title">Recommended: {formatAlgorithm(candidate.algorithm)}</div>
              <div className="rec-sub">Best balance across the leaderboard of candidates tested</div>
            </div>
          </div>
        </div>
      )}

      {run?.interpretation_key_drivers && run.interpretation_key_drivers.length > 0 && (
        <KeyDriversList drivers={run.interpretation_key_drivers} />
      )}

      <div className="stat-row">
        <div className="stat-tile">
          <span className="num mono">{primaryMetricValue !== undefined ? primaryMetricValue.toFixed(2) : "--"}</span>
          <span className="label">{primaryMetricLabel}</span>
        </div>
        <div className="stat-tile">
          <span className="num mono">{run?.row_count_used ?? "--"}</span>
          <span className="label">Rows used to train</span>
        </div>
        <div className="stat-tile" style={{ flexDirection: "row", alignItems: "center" }}>
          <span className="num" style={{ fontSize: "15px" }}>
            Leaderboard
          </span>
          <a className="link" href="#" onClick={(e) => { e.preventDefault(); onSeeFullMetrics(); }}>
            See full metrics &amp; leaderboard →
          </a>
        </div>
      </div>
    </>
  );
}

function AdvancedView({
  leaderboard,
  leaderboardError,
}: {
  leaderboard: LeaderboardData | null;
  leaderboardError: string | null;
}) {
  if (leaderboardError) {
    return (
      <div className="card" style={{ borderColor: "var(--bad)", color: "var(--bad)" }}>
        {leaderboardError}
      </div>
    );
  }
  if (!leaderboard) {
    return <div className="empty-state">Loading leaderboard…</div>;
  }

  const recommended = leaderboard.candidates.find((c) => c.role === "recommended") ?? leaderboard.candidates[0];
  const importance = recommended?.feature_importance ?? [];
  const maxImportance = Math.max(...importance.map((f) => f.importance), 0.0001);

  return (
    <>
      <Leaderboard candidates={leaderboard.candidates} />

      <div className="two-col">
        <div className="card">
          <h3>Feature importance</h3>
          {importance.map((f) => (
            <div className="fi-row" key={f.feature}>
              <span className="mono">{f.feature}</span>
              <div className="fi-track">
                <div className="fi-fill" style={{ width: `${(f.importance / maxImportance) * 100}%` }} />
              </div>
              <span className="mono">{f.importance.toFixed(3)}</span>
            </div>
          ))}
        </div>
        {recommended && (
          <HyperparamsPanel algorithmLabel={formatAlgorithm(recommended.algorithm)} hyperparams={recommended.hyperparams} />
        )}
      </div>

      {leaderboard.run && <RunMetadataFooter run={leaderboard.run} />}
    </>
  );
}
