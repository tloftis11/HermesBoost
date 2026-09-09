import { useState } from "react";
import type { ColumnProfile } from "../types";
import { ColumnCard } from "./ColumnCard";

const INITIAL_VISIBLE = 8;

export function ColumnProfileGrid({ columns }: { columns: ColumnProfile[] }) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? columns : columns.slice(0, INITIAL_VISIBLE);
  const hasMore = columns.length > INITIAL_VISIBLE;

  return (
    <div>
      <p className="panel-title">
        Columns{" "}
        <span>
          {visible.length} of {columns.length}
          {hasMore && (
            <>
              {" · "}
              <button type="button" className="show-all-btn" onClick={() => setShowAll((v) => !v)}>
                {showAll ? "Show fewer" : "Show all"}
              </button>
            </>
          )}
        </span>
      </p>
      <div className="col-grid">
        {visible.map((column) => (
          <ColumnCard key={column.name} column={column} />
        ))}
      </div>
    </div>
  );
}
