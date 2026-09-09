import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { createRiskScore, deleteRiskScore, listRiskScores } from "../api/riskScores";
import { Sidebar } from "../components/Sidebar";
import { useModels } from "../hooks/useModels";
import type { RiskScoreOut } from "../types";

export function RiskScoresPage() {
  const { models } = useModels();
  const [riskScores, setRiskScores] = useState<RiskScoreOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [probabilityModelId, setProbabilityModelId] = useState("");
  const [magnitudeModelId, setMagnitudeModelId] = useState("");
  const [positiveLabel, setPositiveLabel] = useState("True");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const refresh = () => {
    listRiskScores()
      .then(setRiskScores)
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load risk scores"))
      .finally(() => setLoading(false));
  };

  useEffect(refresh, []);

  const classificationModels = models.filter((m) => m.status === "ready" && m.ml_task === "classification");
  const regressionModels = models.filter((m) => m.status === "ready" && m.ml_task === "regression");

  const handleCreate = async () => {
    if (!name.trim() || !probabilityModelId || !magnitudeModelId) return;
    setCreating(true);
    setCreateError(null);
    try {
      await createRiskScore({
        name: name.trim(),
        probability_model_id: probabilityModelId,
        magnitude_model_id: magnitudeModelId,
        positive_label: positiveLabel.trim() || "True",
      });
      setName("");
      setProbabilityModelId("");
      setMagnitudeModelId("");
      setPositiveLabel("True");
      refresh();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Could not create risk score");
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteRiskScore(id);
      refresh();
    } catch {
      // leave the list as-is on failure
    }
  };

  return (
    <div className="shell">
      <Sidebar activeItem="risk-scores" />
      <div className="main">
        <div className="topbar">
          <div className="breadcrumb">Risk Scores</div>
        </div>
        <div className="content">
          <div className="card" style={{ maxWidth: 640, marginBottom: 16 }}>
            <h3>Combine a two-stage model into one risk score</h3>
            <p className="spec-caption">
              Pick a classification model (likelihood) and a regression model (magnitude, given it
              happens). The combined score is computed as probability &times; predicted magnitude,
              refreshed on every request from each model's current active candidate.
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 12 }}>
              <input
                className="search-input"
                style={{ margin: 0 }}
                placeholder="Name (e.g. County measles risk score)"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <select
                className="search-input"
                style={{ margin: 0 }}
                value={probabilityModelId}
                onChange={(e) => setProbabilityModelId(e.target.value)}
              >
                <option value="">Probability model (classification)…</option>
                {classificationModels.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.dataset_name} — {m.algorithm ?? m.id}
                  </option>
                ))}
              </select>
              <select
                className="search-input"
                style={{ margin: 0 }}
                value={magnitudeModelId}
                onChange={(e) => setMagnitudeModelId(e.target.value)}
              >
                <option value="">Magnitude model (regression)…</option>
                {regressionModels.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.dataset_name} — {m.algorithm ?? m.id}
                  </option>
                ))}
              </select>
              <input
                className="search-input"
                style={{ margin: 0 }}
                placeholder="Positive class label (e.g. True, 1, yes)"
                value={positiveLabel}
                onChange={(e) => setPositiveLabel(e.target.value)}
              />
              <button
                type="button"
                className="btn primary"
                disabled={creating || !name.trim() || !probabilityModelId || !magnitudeModelId}
                onClick={handleCreate}
                style={{ alignSelf: "flex-start" }}
              >
                {creating ? "Creating…" : "+ Create risk score"}
              </button>
            </div>

            {createError && (
              <p className="spec-caption" style={{ color: "var(--bad)", marginTop: 8 }}>
                {createError}
              </p>
            )}
          </div>

          {loading ? (
            <div className="empty-state">Loading risk scores…</div>
          ) : error ? (
            <div className="empty-state">{error}</div>
          ) : riskScores.length === 0 ? (
            <div className="empty-state">No risk scores yet.</div>
          ) : (
            <div className="ds-list" style={{ maxWidth: 640 }}>
              {riskScores.map((rs) => (
                <div className="ds-item" key={rs.id} style={{ cursor: "default" }}>
                  <div className="ds-head">
                    <Link to={`/risk-scores/${rs.id}`} className="ds-name">
                      {rs.name}
                    </Link>
                    <button type="button" className="btn ghost" onClick={() => handleDelete(rs.id)}>
                      Delete
                    </button>
                  </div>
                  <div className="ds-meta mono">positive label: {rs.positive_label}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
