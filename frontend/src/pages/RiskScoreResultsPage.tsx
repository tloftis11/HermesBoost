import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { API_URL } from "../api/client";
import { getRiskScore, getRiskScoreResults } from "../api/riskScores";
import { Sidebar } from "../components/Sidebar";
import type { RiskScoreOut, RiskScoreResult } from "../types";

export function RiskScoreResultsPage() {
  const { riskScoreId } = useParams<{ riskScoreId: string }>();
  const [riskScore, setRiskScore] = useState<RiskScoreOut | null>(null);
  const [result, setResult] = useState<RiskScoreResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!riskScoreId) return;
    Promise.all([getRiskScore(riskScoreId), getRiskScoreResults(riskScoreId)])
      .then(([rs, res]) => {
        setRiskScore(rs);
        setResult(res);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load risk score"))
      .finally(() => setLoading(false));
  }, [riskScoreId]);

  return (
    <div className="shell">
      <Sidebar activeItem="risk-scores" />
      <div className="main">
        <div className="topbar">
          <div className="breadcrumb">Risk Scores / {riskScore?.name ?? riskScoreId}</div>
        </div>
        <div className="content">
          {loading ? (
            <div className="empty-state">Loading…</div>
          ) : error ? (
            <div className="empty-state">{error}</div>
          ) : !result || result.rows.length === 0 ? (
            <div className="empty-state">No rows -- check that both underlying models are ready.</div>
          ) : (
            <>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                <p className="panel-title">
                  Ranked by risk score <span>{result.total_row_count}</span>
                </p>
                <a
                  className="btn ghost"
                  href={`${API_URL}/api/v1/risk-scores/${riskScoreId}/scores?format=csv`}
                  download
                >
                  Download CSV
                </a>
              </div>
              <div className="card">
                <table>
                  <thead>
                    <tr>
                      <th>Entity</th>
                      <th>Probability</th>
                      <th>Predicted magnitude</th>
                      <th>Risk score</th>
                      <th>Score date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.map((r) => (
                      <tr key={r.entity_id}>
                        <td className="mono">{r.entity_id}</td>
                        <td className="mono">{r.probability.toFixed(3)}</td>
                        <td className="mono">{r.predicted_magnitude.toFixed(2)}</td>
                        <td className="mono">{r.risk_score.toFixed(2)}</td>
                        <td className="mono">{r.score_date}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
