import type { ModelCandidate } from "../types";

const ALGORITHM_LABEL: Record<string, string> = {
  logistic_regression: "Logistic Regression",
  linear_regression: "Linear Regression",
  random_forest: "Random Forest",
  xgboost: "XGBoost",
  lgbm: "Gradient Boosted Trees",
  rf: "Random Forest",
  extra_tree: "Extra Trees",
  lrl1: "L1 Logistic Regression",
};

export function formatAlgorithm(algorithm: string): string {
  if (algorithm.startsWith("flaml_")) {
    const inner = algorithm.slice("flaml_".length);
    return `${ALGORITHM_LABEL[inner] ?? inner} (FLAML-tuned)`;
  }
  return ALGORITHM_LABEL[algorithm] ?? algorithm;
}

function formatMetric(value: number | boolean | null | undefined): string {
  return typeof value === "number" ? value.toFixed(2) : "--";
}

interface LeaderboardProps {
  candidates: ModelCandidate[];
  activeCandidateId?: string | null;
  onPromote?: (candidateId: string) => void;
  promoting?: string | null;
}

export function Leaderboard({ candidates, activeCandidateId, onPromote, promoting }: LeaderboardProps) {
  const mlTask = candidates[0]?.ml_task;
  const isClassification = mlTask === "classification";

  return (
    <div className="card">
      <h3>Leaderboard</h3>
      <table>
        <thead>
          <tr>
            <th>Model</th>
            <th>Algorithm</th>
            {isClassification ? (
              <>
                <th>AUC</th>
                <th>Precision</th>
                <th>Recall</th>
                <th>Calibration err.</th>
                <th>Best-F1 threshold (P/R)</th>
              </>
            ) : (
              <>
                <th>R&sup2;</th>
                <th>RMSE</th>
                <th>MAE</th>
              </>
            )}
            <th>Train time</th>
            {onPromote && <th></th>}
          </tr>
        </thead>
        <tbody>
          {candidates.map((c) => {
            const isActive = activeCandidateId ? c.id === activeCandidateId : c.role === "recommended";
            return (
              <tr key={c.id} className={isActive ? "highlight" : undefined}>
                <td className="mono">{c.role === "recommended" ? "Recommended" : "Baseline"}</td>
                <td>
                  {formatAlgorithm(c.algorithm)}
                  {c.metrics.class_weighted === true && (
                    <span className="pill" style={{ marginLeft: 6 }} title="Class weighting applied -- rare positive class">
                      weighted
                    </span>
                  )}
                </td>
                {isClassification ? (
                  <>
                    <td className="mono">{formatMetric(c.metrics.auc)}</td>
                    <td className="mono">{formatMetric(c.metrics.precision)}</td>
                    <td className="mono">{formatMetric(c.metrics.recall)}</td>
                    <td className="mono">{formatMetric(c.metrics.calibration_error)}</td>
                    <td className="mono">
                      {typeof c.metrics.threshold_at_max_f1 === "number"
                        ? `${c.metrics.threshold_at_max_f1.toFixed(2)} (${formatMetric(c.metrics.precision_at_max_f1)}/${formatMetric(c.metrics.recall_at_max_f1)})`
                        : "--"}
                    </td>
                  </>
                ) : (
                  <>
                    <td className="mono">{formatMetric(c.metrics.r2)}</td>
                    <td className="mono">{formatMetric(c.metrics.rmse)}</td>
                    <td className="mono">{formatMetric(c.metrics.mae)}</td>
                  </>
                )}
                <td className="mono">{c.train_time_seconds === null ? "--" : `${Number(c.train_time_seconds).toFixed(1)}s`}</td>
                {onPromote && (
                  <td>
                    {isActive ? (
                      <span className="pill good">Active</span>
                    ) : (
                      <button
                        type="button"
                        className="btn ghost"
                        disabled={promoting === c.id}
                        onClick={() => onPromote(c.id)}
                      >
                        {promoting === c.id ? "Promoting…" : "Promote"}
                      </button>
                    )}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
