import { Link } from "react-router-dom";
import type { ModelListItem as ModelListItemType } from "../types";

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

function StatusBadge({ status }: { status: ModelListItemType["status"] }) {
  if (status === "ready") return <span className="pill good">Ready</span>;
  if (status === "error") return <span className="pill bad">Error</span>;
  return <span className="pill warn">Training</span>;
}

function formatMeta(model: ModelListItemType): string {
  const parts: string[] = [];
  if (model.algorithm) {
    parts.push(model.algorithm);
  }
  if (model.primary_metric_label && model.primary_metric_value !== null) {
    parts.push(`${model.primary_metric_label} ${model.primary_metric_value.toFixed(2)}`);
  }
  parts.push(formatRelativeTime(model.updated_at));
  return parts.join(" · ");
}

interface ModelListItemProps {
  model: ModelListItemType;
}

export function ModelListItem({ model }: ModelListItemProps) {
  return (
    <Link to={`/models/${model.id}`} className="ds-item" style={{ display: "block" }}>
      <div className="ds-head">
        <span className="ds-name mono">{model.task_description ?? model.dataset_name}</span>
        <StatusBadge status={model.status} />
      </div>
      <div className="ds-meta">{formatMeta(model)}</div>
    </Link>
  );
}
