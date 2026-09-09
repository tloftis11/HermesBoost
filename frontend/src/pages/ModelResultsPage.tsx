import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getLeaderboard, getScores, promoteCandidate, scoreModel } from "../api/models";
import { getModelingSpec } from "../api/modelingSpecs";
import { HyperparamsPanel } from "../components/HyperparamsPanel";
import { KeyDriversList } from "../components/KeyDriversList";
import { Leaderboard, formatAlgorithm } from "../components/Leaderboard";
import { RunMetadataFooter } from "../components/RunMetadataFooter";
import { ScoreResultsTable } from "../components/ScoreResultsTable";
import { Sidebar } from "../components/Sidebar";
import { useModelRun } from "../hooks/useModelRun";
import type { Leaderboard as LeaderboardData, ModelGuided, ModelingSpec, ScoreRun } from "../types";

type ViewMode = "guided" | "advanced" | "scores";

const SCORE_POLL_INTERVAL_MS = 2000;

function exportLeaderboardCsv(leaderboard: LeaderboardData, modelId: string) {
  const headers = ["role", "algorithm", "metrics", "hyperparams", "train_time_seconds"];
  const escape = (v: string) => `"${v.replace(/"/g, '""')}"`;
  const lines = [headers.join(",")];
  for (const c of leaderboard.candidates) {
    lines.push(
      [
        escape(c.role),
        escape(formatAlgorithm(c.algorithm)),
        escape(JSON.stringify(c.metrics)),
        escape(JSON.stringify(c.hyperparams ?? {})),
        escape(c.train_time_seconds ?? ""),
      ].join(","),
    );
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `leaderboard-${modelId}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function ModelResultsPage() {
  const { modelId } = useParams<{ modelId: string }>();
  const { model, loading } = useModelRun(modelId ?? null);

  const [spec, setSpec] = useState<ModelingSpec | null>(null);
  const [view, setView] = useState<ViewMode>("guided");
  const [leaderboard, setLeaderboard] = useState<LeaderboardData | null>(null);
  const [leaderboardError, setLeaderboardError] = useState<string | null>(null);
  const [activeCandidateId, setActiveCandidateId] = useState<string | null>(null);
  const [promoting, setPromoting] = useState<string | null>(null);

  useEffect(() => {
    if (!model) return;
    getModelingSpec(model.modeling_spec_id)
      .then((detail) => setSpec(detail.spec))
      .catch(() => {});
  }, [model?.modeling_spec_id]);

  useEffect(() => {
    setActiveCandidateId(model?.active_candidate?.id ?? null);
  }, [model?.active_candidate?.id]);

  useEffect(() => {
    if (!modelId || !model || model.status === "training") return;
    getLeaderboard(modelId)
      .then(setLeaderboard)
      .catch((err) => setLeaderboardError(err instanceof Error ? err.message : "Could not load leaderboard"));
  }, [modelId, model?.status]);

  const handlePromote = async (candidateId: string) => {
    if (!modelId) return;
    setPromoting(candidateId);
    try {
      await promoteCandidate(modelId, candidateId);
      setActiveCandidateId(candidateId);
    } catch {
      // leave the active candidate as-is on failure
    } finally {
      setPromoting(null);
    }
  };

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
                <button
                  type="button"
                  className={`seg-btn${view === "scores" ? " active" : ""}`}
                  onClick={() => setView("scores")}
                >
                  Scores
                </button>
              </div>
              <button
                type="button"
                className="btn ghost"
                disabled={!leaderboard}
                onClick={() => modelId && leaderboard && exportLeaderboardCsv(leaderboard, modelId)}
              >
                Export
              </button>
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
          ) : view === "advanced" ? (
            <AdvancedView
              leaderboard={leaderboard}
              leaderboardError={leaderboardError}
              activeCandidateId={activeCandidateId}
              onPromote={handlePromote}
              promoting={promoting}
            />
          ) : (
            <ScoresView modelId={modelId!} />
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
  activeCandidateId,
  onPromote,
  promoting,
}: {
  leaderboard: LeaderboardData | null;
  leaderboardError: string | null;
  activeCandidateId: string | null;
  onPromote: (candidateId: string) => void;
  promoting: string | null;
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

  const active =
    leaderboard.candidates.find((c) => c.id === activeCandidateId) ??
    leaderboard.candidates.find((c) => c.role === "recommended") ??
    leaderboard.candidates[0];
  const importance = active?.feature_importance ?? [];
  const maxImportance = Math.max(...importance.map((f) => f.importance), 0.0001);

  return (
    <>
      <Leaderboard
        candidates={leaderboard.candidates}
        activeCandidateId={activeCandidateId}
        onPromote={onPromote}
        promoting={promoting}
      />

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
        {active && (
          <HyperparamsPanel algorithmLabel={formatAlgorithm(active.algorithm)} hyperparams={active.hyperparams} />
        )}
      </div>

      {leaderboard.run && <RunMetadataFooter run={leaderboard.run} />}
    </>
  );
}

function ScoresView({ modelId }: { modelId: string }) {
  const [scoreRun, setScoreRun] = useState<ScoreRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const fetchScores = useCallback(async () => {
    try {
      const data = await getScores(modelId);
      setScoreRun(data);
      if (data.run?.status !== "running" && pollRef.current !== null) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    } catch {
      // leave prior state on a transient fetch failure
    } finally {
      setLoading(false);
    }
  }, [modelId]);

  useEffect(() => {
    fetchScores();
    return () => {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [fetchScores]);

  const handleScoreNow = async () => {
    setError(null);
    setStarting(true);
    try {
      await scoreModel(modelId);
      await fetchScores();
      if (pollRef.current === null) {
        pollRef.current = window.setInterval(fetchScores, SCORE_POLL_INTERVAL_MS);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start scoring");
    } finally {
      setStarting(false);
    }
  };

  if (loading) {
    return <div className="empty-state">Loading scores…</div>;
  }

  const run = scoreRun?.run ?? null;
  const isRunning = starting || run?.status === "running";

  return (
    <>
      <div className="status-row">
        {run && (
          <span className={`pill ${run.status === "completed" ? "good" : run.status === "error" ? "bad" : "warn"}`}>
            {run.status}
          </span>
        )}
        {run?.completed_at && <span>Last scored {new Date(run.completed_at).toLocaleString()}</span>}
        <button type="button" className="btn primary" disabled={isRunning} onClick={handleScoreNow}>
          {isRunning ? "Scoring…" : "Score now"}
        </button>
      </div>

      {error && (
        <div className="card" style={{ borderColor: "var(--bad)", color: "var(--bad)" }}>
          {error}
        </div>
      )}
      {run?.status === "error" && (
        <div className="card" style={{ borderColor: "var(--bad)", color: "var(--bad)" }}>
          {run.error_message ?? "Scoring failed."}
        </div>
      )}
      {run?.warnings && run.warnings.length > 0 && (
        <div className="run-warnings">
          {run.warnings.map((w, i) => (
            <span className="pill warn" key={i}>
              {w}
            </span>
          ))}
        </div>
      )}

      {!run ? (
        <div className="empty-state">
          No scores yet -- click "Score now" to run this model against the latest data.
        </div>
      ) : (
        <>
          {scoreRun && scoreRun.rows.length > 0 && (
            <p className="spec-caption">
              Showing {scoreRun.rows.length} of {scoreRun.total_row_count ?? scoreRun.rows.length} rows.
            </p>
          )}
          <ScoreResultsTable rows={scoreRun?.rows ?? []} />
        </>
      )}
    </>
  );
}
