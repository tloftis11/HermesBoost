import { useMemo, useState } from "react";
import type { Dataset } from "../types";
import { DatasetListItem } from "./DatasetListItem";
import { UploadDropzone } from "./UploadDropzone";

interface DatasetListProps {
  datasets: Dataset[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onTriggerUpload: () => void;
  uploading: boolean;
}

export function DatasetList({ datasets, selectedId, onSelect, onTriggerUpload, uploading }: DatasetListProps) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return datasets;
    return datasets.filter((d) => d.name.toLowerCase().includes(q));
  }, [datasets, query]);

  return (
    <div>
      <p className="panel-title">
        Your datasets <span>{datasets.length}</span>
      </p>
      <input
        className="search-input"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search datasets"
      />
      <div className="ds-list">
        {filtered.length === 0 ? (
          <div className="empty-state">
            {datasets.length === 0 ? "No datasets yet -- upload one to get started." : "No matches."}
          </div>
        ) : (
          filtered.map((dataset) => (
            <DatasetListItem
              key={dataset.id}
              dataset={dataset}
              selected={dataset.id === selectedId}
              onSelect={onSelect}
            />
          ))
        )}
      </div>
      <UploadDropzone onTriggerUpload={onTriggerUpload} uploading={uploading} />
    </div>
  );
}
