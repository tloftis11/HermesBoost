import type { ModelRun } from "../types";

interface RunMetadataFooterProps {
  run: ModelRun;
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "--";
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function RunMetadataFooter({ run }: RunMetadataFooterProps) {
  return (
    <div className="card">
      <div className="run-meta mono">
        <span>Run ID: {run.id}</span>
        <span>Task: {run.ml_task ?? "--"}</span>
        <span>Rows used: {run.row_count_used ?? "--"}</span>
        <span>Interpretation model: {run.interpretation_model ?? "--"}</span>
        <span>Trained: {formatDateTime(run.completed_at ?? run.started_at)}</span>
      </div>
      {run.warnings && run.warnings.length > 0 && (
        <div className="run-warnings">
          {run.warnings.map((w, i) => (
            <div className="pill warn" key={i}>
              {w}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
