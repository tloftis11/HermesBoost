import type { DatasetStatus } from "../types";

export function StatusPill({ status }: { status: DatasetStatus }) {
  if (status === "profiled") {
    return null;
  }
  if (status === "error") {
    return <span className="pill bad">Error</span>;
  }
  return <span className="pill warn">Processing</span>;
}
