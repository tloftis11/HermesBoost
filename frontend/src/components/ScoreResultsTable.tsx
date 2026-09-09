import type { ScoredRow } from "../types";

interface ScoreResultsTableProps {
  rows: ScoredRow[];
}

export function ScoreResultsTable({ rows }: ScoreResultsTableProps) {
  if (rows.length === 0) {
    return <div className="empty-state">No scored rows yet.</div>;
  }
  const isClassification = rows[0].predicted_label !== null;

  return (
    <div className="card">
      <table>
        <thead>
          <tr>
            <th>Entity</th>
            <th>{isClassification ? "Predicted label" : "Predicted value"}</th>
            {isClassification && <th>Probability</th>}
            <th>Score date</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td className="mono">{r.entity_id}</td>
              <td className="mono">
                {isClassification ? r.predicted_label : r.predicted_value?.toFixed(3) ?? "--"}
              </td>
              {isClassification && (
                <td className="mono">
                  {r.predicted_probability !== null ? r.predicted_probability.toFixed(2) : "--"}
                </td>
              )}
              <td className="mono">{r.score_date}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
