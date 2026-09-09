interface TopbarProps {
  selectedDatasetName: string | null;
  onUploadClick: () => void;
  uploading: boolean;
}

export function Topbar({ selectedDatasetName, onUploadClick, uploading }: TopbarProps) {
  return (
    <div className="topbar">
      <div className="breadcrumb">
        Datasets{selectedDatasetName ? <> / <b className="mono">{selectedDatasetName}</b></> : null}
      </div>
      <div className="topbar-right">
        <button type="button" className="btn ghost" disabled title="Coming soon">
          Search
        </button>
        <button type="button" className="btn primary" onClick={onUploadClick} disabled={uploading}>
          <svg width="14" height="14" viewBox="0 0 20 20" fill="none">
            <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
            <path d="M10 6.5v7M6.5 10h7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
          {uploading ? "Uploading…" : "Upload dataset"}
        </button>
      </div>
    </div>
  );
}
