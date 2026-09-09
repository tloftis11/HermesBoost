interface HyperparamsPanelProps {
  algorithmLabel: string;
  hyperparams: Record<string, unknown> | null;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "--";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4);
  return String(value);
}

export function HyperparamsPanel({ algorithmLabel, hyperparams }: HyperparamsPanelProps) {
  const entries = Object.entries(hyperparams ?? {});

  return (
    <div className="card">
      <h3>Hyperparameters &mdash; {algorithmLabel}</h3>
      {entries.length === 0 ? (
        <p className="spec-caption">No hyperparameters recorded for this candidate.</p>
      ) : (
        <div className="kv-grid">
          {entries.map(([key, value]) => (
            <div className="kv-row" key={key}>
              <span>{key}</span>
              <span className="mono">{formatValue(value)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
