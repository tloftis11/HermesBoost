import type { Cadence, ColumnProfile, ModelingSpec } from "../types";

interface SpecCardProps {
  spec: ModelingSpec;
  availableColumns: ColumnProfile[];
  onPatch: (patch: { candidate_features?: string[]; retrain_cadence?: Cadence; score_cadence?: Cadence }) => void;
  disabled: boolean;
}

const TASK_TYPE_LABEL: Record<string, string> = {
  risk_scoring: "Risk scoring",
  classification: "Classification",
  regression: "Regression",
  time_series_forecast: "Time-series forecast",
  clustering: "Clustering",
  anomaly_detection: "Anomaly detection",
};

export function SpecCard({ spec, availableColumns, onPatch, disabled }: SpecCardProps) {
  const addableColumns = availableColumns.filter((c) => !spec.candidate_features.includes(c.name));

  const removeFeature = (name: string) => {
    onPatch({ candidate_features: spec.candidate_features.filter((f) => f !== name) });
  };

  const addFeature = (name: string) => {
    if (!name) return;
    onPatch({ candidate_features: [...spec.candidate_features, name] });
  };

  const hasSpec = Boolean(spec.task_type);

  return (
    <div className="spec-card">
      <div className="spec-head">Proposed modeling spec</div>

      {!hasSpec ? (
        <p className="spec-caption">
          Describe what you want to do -- once there's enough to go on, a proposed spec will show up here.
        </p>
      ) : (
        <>
          <div className="spec-field">
            <span className="spec-label">Task type</span>
            <div className="spec-value stacked">
              <span>{TASK_TYPE_LABEL[spec.task_type ?? ""] ?? spec.task_type}</span>
              {spec.task_description && (
                <span className="spec-value-sub">{spec.task_description}</span>
              )}
            </div>
          </div>

          <div className="spec-field">
            <span className="spec-label">Target</span>
            <div className="spec-value mono">{spec.target || "--"}</div>
          </div>

          <div className="spec-field">
            <span className="spec-label">Candidate features</span>
            <div className="chip-row">
              {spec.candidate_features.map((name) => (
                <span className="chip mono" key={name}>
                  {name}
                  <button
                    type="button"
                    className="chip-remove"
                    onClick={() => removeFeature(name)}
                    disabled={disabled}
                    aria-label={`Remove ${name}`}
                  >
                    ×
                  </button>
                </span>
              ))}
              {addableColumns.length > 0 && (
                <select
                  className="add-feature-select"
                  value=""
                  disabled={disabled}
                  onChange={(e) => addFeature(e.target.value)}
                >
                  <option value="">+ Add feature</option>
                  {addableColumns.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name}
                    </option>
                  ))}
                </select>
              )}
            </div>
          </div>

          <div className="spec-field">
            <span className="spec-label">Evaluation metric</span>
            <div className="spec-value">{spec.evaluation_metric || "--"}</div>
          </div>

          <div className="spec-field">
            <span className="spec-label">Retrain cadence</span>
            <select
              className="spec-select"
              value={spec.retrain_cadence}
              disabled={disabled}
              onChange={(e) => onPatch({ retrain_cadence: e.target.value as Cadence })}
            >
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </div>

          <div className="spec-field">
            <span className="spec-label">Score cadence</span>
            <select
              className="spec-select"
              value={spec.score_cadence}
              disabled={disabled}
              onChange={(e) => onPatch({ score_cadence: e.target.value as Cadence })}
            >
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </div>
        </>
      )}

      <div className="spec-foot">
        <button type="button" className="btn primary" style={{ justifyContent: "center" }} disabled title="Coming soon">
          Build models →
        </button>
        <p className="spec-caption">
          HermesBoost proposes this from your description -- you're always in control before anything runs.
        </p>
      </div>
    </div>
  );
}
