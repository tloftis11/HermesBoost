import type { ColumnProfile } from "../types";

const DTYPE_PILL_LABEL: Record<ColumnProfile["dtype"], string> = {
  numeric: "numeric",
  categorical: "category",
  id: "id",
};

function formatNumber(n: number): string {
  return Number.isInteger(n) ? n.toLocaleString() : n.toFixed(1);
}

function statsLine(column: ColumnProfile): string {
  const nullPct = `${(column.null_rate * 100).toFixed(1)}% null`;
  if (column.dtype === "numeric") {
    const range = column.min !== null && column.max !== null
      ? `${formatNumber(column.min)}–${formatNumber(column.max)}`
      : null;
    const mean = column.mean !== null ? `mean ${formatNumber(column.mean)}` : null;
    return [nullPct, range, mean].filter(Boolean).join(" · ");
  }
  return `${nullPct} · ${column.distinct_count.toLocaleString()} distinct`;
}

function MiniHistogram({ histogram }: { histogram: number[] }) {
  const max = Math.max(...histogram, 1);
  return (
    <div className="mini-hist">
      {histogram.map((count, i) => (
        <span key={i} style={{ height: `${Math.max((count / max) * 100, 3)}%` }} />
      ))}
    </div>
  );
}

function TopBars({ topValues }: { topValues: { value: string; count: number }[] }) {
  const max = Math.max(...topValues.map((tv) => tv.count), 1);
  return (
    <div className="top-bars">
      {topValues.slice(0, 3).map((tv) => (
        <div className="top-bar-row" key={tv.value}>
          {tv.value}
          <div className="track">
            <div className="fill" style={{ width: `${(tv.count / max) * 100}%` }} />
          </div>
          {tv.count.toLocaleString()}
        </div>
      ))}
    </div>
  );
}

export function ColumnCard({ column }: { column: ColumnProfile }) {
  return (
    <div className="col-card">
      <div className="col-card-head">
        <span className="col-name mono">{column.name}</span>
        <span className="pill neutral">{DTYPE_PILL_LABEL[column.dtype]}</span>
      </div>
      <div className="col-stats">{statsLine(column)}</div>
      {column.dtype === "numeric" && column.histogram && <MiniHistogram histogram={column.histogram} />}
      {column.dtype === "categorical" && column.top_values && <TopBars topValues={column.top_values} />}
    </div>
  );
}
