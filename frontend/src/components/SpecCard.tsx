import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { buildModel } from "../api/models";
import type { Cadence, ColumnProfile, Dataset, DatasetProfile, JoinDataset, JoinType, ModelingSpec } from "../types";

interface SpecCardProps {
  spec: ModelingSpec;
  availableColumns: ColumnProfile[];
  onPatch: (patch: { candidate_features?: string[]; retrain_cadence?: Cadence; score_cadence?: Cadence }) => void;
  disabled: boolean;
  baseDatasetName: string;
  baseColumns: ColumnProfile[];
  joinDatasets: JoinDataset[];
  attachableDatasets: Dataset[];
  getProfileForDataset: (datasetId: string) => Promise<DatasetProfile>;
  onAttachDataset: (datasetId: string, joinKeyColumn: string, joinType: JoinType) => Promise<void>;
  onDetachDataset: (joinId: string) => void;
  existingModelId: string | null;
}

const TASK_TYPE_LABEL: Record<string, string> = {
  risk_scoring: "Risk scoring",
  classification: "Classification",
  regression: "Regression",
  time_series_forecast: "Time-series forecast",
  clustering: "Clustering",
  anomaly_detection: "Anomaly detection",
};

export function SpecCard({
  spec,
  availableColumns,
  onPatch,
  disabled,
  baseDatasetName,
  baseColumns,
  joinDatasets,
  attachableDatasets,
  getProfileForDataset,
  onAttachDataset,
  onDetachDataset,
  existingModelId,
}: SpecCardProps) {
  const navigate = useNavigate();
  const [building, setBuilding] = useState(false);
  const [buildError, setBuildError] = useState<string | null>(null);
  const addableColumns = availableColumns.filter((c) => !spec.candidate_features.includes(c.name));

  const [attachDatasetId, setAttachDatasetId] = useState("");
  const [attachJoinKey, setAttachJoinKey] = useState("");
  const [attachJoinType, setAttachJoinType] = useState<JoinType>("left");
  const [attachCandidateColumns, setAttachCandidateColumns] = useState<string[]>([]);
  const [attaching, setAttaching] = useState(false);
  const [attachError, setAttachError] = useState<string | null>(null);

  const canBuild =
    Boolean(spec.task_type) && Boolean(spec.target) && spec.candidate_features.length > 0 && !building;

  const handleBuild = async () => {
    setBuildError(null);
    setBuilding(true);
    try {
      const { model_id } = await buildModel(spec.id);
      navigate(`/models/${model_id}`);
    } catch (err) {
      setBuildError(err instanceof Error ? err.message : "Could not start training");
      setBuilding(false);
    }
  };

  const removeFeature = (name: string) => {
    onPatch({ candidate_features: spec.candidate_features.filter((f) => f !== name) });
  };

  const addFeature = (name: string) => {
    if (!name) return;
    onPatch({ candidate_features: [...spec.candidate_features, name] });
  };

  const resetAttachForm = () => {
    setAttachDatasetId("");
    setAttachJoinKey("");
    setAttachCandidateColumns([]);
    setAttachJoinType("left");
  };

  const handleSelectAttachDataset = async (id: string) => {
    setAttachDatasetId(id);
    setAttachJoinKey("");
    setAttachCandidateColumns([]);
    setAttachError(null);
    if (!id) return;
    try {
      const profile = await getProfileForDataset(id);
      const baseNames = new Set(baseColumns.map((c) => c.name));
      const common = (profile.columns ?? []).filter((c) => baseNames.has(c.name)).map((c) => c.name);
      setAttachCandidateColumns(common);
      if (common.length > 0) setAttachJoinKey(common[0]);
    } catch {
      setAttachError("Could not load that dataset's profile.");
    }
  };

  const handleConfirmAttach = async () => {
    if (!attachDatasetId || !attachJoinKey) return;
    setAttaching(true);
    setAttachError(null);
    try {
      await onAttachDataset(attachDatasetId, attachJoinKey, attachJoinType);
      resetAttachForm();
    } catch (err) {
      setAttachError(err instanceof Error ? err.message : "Could not attach that dataset");
    } finally {
      setAttaching(false);
    }
  };

  const hasSpec = Boolean(spec.task_type);

  return (
    <div className="spec-card">
      <div className="spec-head">Proposed modeling spec</div>

      <div className="spec-field">
        <span className="spec-label">Data sources</span>
        <div className="chip-row">
          <span className="chip mono">{baseDatasetName}</span>
          {joinDatasets.map((jd) => (
            <span className="chip mono" key={jd.id}>
              {jd.dataset_name} · {jd.join_key_column} ({jd.join_type})
              <button
                type="button"
                className="chip-remove"
                onClick={() => onDetachDataset(jd.id)}
                disabled={disabled}
                aria-label={`Detach ${jd.dataset_name}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
        {attachableDatasets.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 4 }}>
            <select
              className="spec-select"
              value={attachDatasetId}
              disabled={disabled || attaching}
              onChange={(e) => handleSelectAttachDataset(e.target.value)}
            >
              <option value="">+ Attach a dataset</option>
              {attachableDatasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
            {attachDatasetId && attachCandidateColumns.length === 0 && (
              <p className="spec-caption" style={{ color: "var(--bad)" }}>
                No shared columns to join on -- can't attach this dataset.
              </p>
            )}
            {attachCandidateColumns.length > 0 && (
              <>
                <select
                  className="spec-select"
                  value={attachJoinKey}
                  disabled={disabled || attaching}
                  onChange={(e) => setAttachJoinKey(e.target.value)}
                >
                  {attachCandidateColumns.map((name) => (
                    <option key={name} value={name}>
                      Join on {name}
                    </option>
                  ))}
                </select>
                <select
                  className="spec-select"
                  value={attachJoinType}
                  disabled={disabled || attaching}
                  onChange={(e) => setAttachJoinType(e.target.value as JoinType)}
                >
                  <option value="left">Left join -- keep all rows from {baseDatasetName}</option>
                  <option value="inner">Inner join -- only matching rows</option>
                </select>
                <button
                  type="button"
                  className="btn ghost"
                  style={{ justifyContent: "center" }}
                  disabled={disabled || attaching}
                  onClick={handleConfirmAttach}
                >
                  {attaching ? "Attaching…" : "Attach dataset"}
                </button>
              </>
            )}
            {attachError && (
              <p className="spec-caption" style={{ color: "var(--bad)" }}>
                {attachError}
              </p>
            )}
          </div>
        )}
      </div>

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
        {existingModelId && (
          <Link
            to={`/models/${existingModelId}`}
            className="btn ghost"
            style={{ justifyContent: "center" }}
          >
            View model →
          </Link>
        )}
        <button
          type="button"
          className="btn primary"
          style={{ justifyContent: "center" }}
          disabled={!canBuild}
          title={canBuild ? undefined : "Set a target and at least one candidate feature first"}
          onClick={handleBuild}
        >
          {building ? "Starting…" : existingModelId ? "Retrain →" : "Build models →"}
        </button>
        {buildError && (
          <p className="spec-caption" style={{ color: "var(--bad)" }}>
            {buildError}
          </p>
        )}
        <p className="spec-caption">
          HermesBoost proposes this from your description -- you're always in control before anything runs.
        </p>
      </div>
    </div>
  );
}
