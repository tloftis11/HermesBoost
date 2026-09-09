import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { API_URL } from "../api/client";
import { getRiskScore, getRiskScoreResults, getRiskScoreUsage } from "../api/riskScores";
import { Sidebar } from "../components/Sidebar";
import type { RiskScoreOut, RiskScoreResult, UsageDoc } from "../types";

export function RiskScoreResultsPage() {
  const { riskScoreId } = useParams<{ riskScoreId: string }>();
  const [riskScore, setRiskScore] = useState<RiskScoreOut | null>(null);
  const [result, setResult] = useState<RiskScoreResult | null>(null);
  const [usage, setUsage] = useState<UsageDoc | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!riskScoreId) return;
    Promise.all([getRiskScore(riskScoreId), getRiskScoreResults(riskScoreId)])
      .then(([rs, res]) => {
        setRiskScore(rs);
        setResult(res);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load risk score"))
      .finally(() => setLoading(false));
    getRiskScoreUsage(riskScoreId).then(setUsage).catch(() => {});
  }, [riskScoreId]);

  const handleCopy = () => {
    if (!usage) return;
    navigator.clipboard?.writeText(usage.curl_example).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

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

              {usage && (
                <div className="card" style={{ maxWidth: 640, marginTop: 16 }}>
                  <h3>Using this risk score via API</h3>
                  <p className="spec-caption">{usage.what_it_predicts}</p>
                  <table style={{ marginTop: 12 }}>
                    <thead>
                      <tr>
                        <th>Field</th>
                        <th>Meaning</th>
                      </tr>
                    </thead>
                    <tbody>
                      {usage.response_fields.map((f) => (
                        <tr key={f.field}>
                          <td className="mono">{f.field}</td>
                          <td>{f.meaning}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div
                    style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 12 }}
                  >
                    <span className="spec-label">Example request</span>
                    <button type="button" className="btn ghost" onClick={handleCopy}>
                      {copied ? "Copied!" : "Copy"}
                    </button>
                  </div>
                  <pre className="card mono" style={{ marginTop: 6, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                    {usage.curl_example}
                  </pre>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
