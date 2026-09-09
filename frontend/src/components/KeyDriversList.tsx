import type { KeyDriver } from "../types";

interface KeyDriversListProps {
  drivers: KeyDriver[];
}

export function KeyDriversList({ drivers }: KeyDriversListProps) {
  const maxImportance = Math.max(...drivers.map((d) => d.relative_importance), 0.0001);

  return (
    <div className="card" style={{ flex: 1, overflow: "hidden" }}>
      <h3>Key drivers</h3>
      {drivers.map((d) => (
        <div className="driver-row" key={d.feature}>
          <span className="driver-name mono">{d.feature}</span>
          <div className="driver-track">
            <div className="driver-fill" style={{ width: `${(d.relative_importance / maxImportance) * 100}%` }} />
          </div>
          <span className="driver-desc">{d.plain_description}</span>
        </div>
      ))}
    </div>
  );
}
