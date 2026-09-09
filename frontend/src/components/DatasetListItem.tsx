import type { Dataset } from "../types";
import { StatusPill } from "./StatusPill";

function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString);
  const diffMs = Date.now() - date.getTime();
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  return `${diffDay}d ago`;
}

function formatMeta(dataset: Dataset): string {
  const parts: string[] = [];
  if (dataset.row_count !== null) {
    parts.push(`${dataset.row_count.toLocaleString()} rows`);
  }
  if (dataset.column_count !== null) {
    parts.push(`${dataset.column_count} cols`);
  }
  parts.push(formatRelativeTime(dataset.created_at));
  return parts.join(" · ");
}

interface DatasetListItemProps {
  dataset: Dataset;
  selected: boolean;
  onSelect: (id: string) => void;
}

export function DatasetListItem({ dataset, selected, onSelect }: DatasetListItemProps) {
  return (
    <div
      className={`ds-item${selected ? " selected" : ""}`}
      onClick={() => onSelect(dataset.id)}
      role="button"
      tabIndex={0}
    >
      <div className="ds-head">
        <span className="ds-name mono">{dataset.name}</span>
        <StatusPill status={dataset.status} />
      </div>
      <div className="ds-meta">
        {dataset.status === "error" ? dataset.error_message ?? "Profiling failed" : formatMeta(dataset)}
      </div>
    </div>
  );
}
