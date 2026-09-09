import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createDatasetSeries, listDatasetSeries, uploadDataset } from "../api/datasets";
import { AiSummaryCard } from "../components/AiSummaryCard";
import { ColumnProfileGrid } from "../components/ColumnProfileGrid";
import { DatasetList } from "../components/DatasetList";
import { Sidebar } from "../components/Sidebar";
import { StatusPill } from "../components/StatusPill";
import { Topbar } from "../components/Topbar";
import { useDatasetProfile } from "../hooks/useDatasetProfile";
import { useDatasets } from "../hooks/useDatasets";
import type { DatasetSeries } from "../types";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function UploadProfilePage() {
  const navigate = useNavigate();
  const { datasets, loading, error, addDataset } = useDatasets();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [seriesList, setSeriesList] = useState<DatasetSeries[]>([]);
  const [showSeriesPanel, setShowSeriesPanel] = useState(false);
  const [seriesMode, setSeriesMode] = useState<"existing" | "new">("existing");
  const [selectedSeriesId, setSelectedSeriesId] = useState("");
  const [newSeriesName, setNewSeriesName] = useState("");
  const [asOfDate, setAsOfDate] = useState(todayIso());
  const [seriesFile, setSeriesFile] = useState<File | null>(null);
  const [seriesUploading, setSeriesUploading] = useState(false);
  const [seriesError, setSeriesError] = useState<string | null>(null);
  const seriesFileInputRef = useRef<HTMLInputElement>(null);

  const { profile } = useDatasetProfile(selectedId);
  const selectedDataset = datasets.find((d) => d.id === selectedId) ?? null;

  useEffect(() => {
    if (!selectedId && datasets.length > 0) {
      setSelectedId(datasets[0].id);
    }
  }, [datasets, selectedId]);

  useEffect(() => {
    listDatasetSeries().then(setSeriesList).catch(() => {});
  }, []);

  const handleTriggerUpload = () => fileInputRef.current?.click();

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file later
    if (!file) return;

    setUploading(true);
    setUploadError(null);
    try {
      const created = await uploadDataset(file);
      addDataset({
        id: created.id,
        name: file.name,
        status: "profiling",
        row_count: null,
        column_count: null,
        error_message: null,
        series_id: null,
        as_of_date: null,
        created_at: new Date().toISOString(),
      });
      setSelectedId(created.id);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleSeriesSubmit = async () => {
    if (!seriesFile) {
      setSeriesError("Choose a file first.");
      return;
    }
    if (seriesMode === "existing" && !selectedSeriesId) {
      setSeriesError("Pick a series, or switch to creating a new one.");
      return;
    }
    if (seriesMode === "new" && !newSeriesName.trim()) {
      setSeriesError("Name the new series.");
      return;
    }

    setSeriesUploading(true);
    setSeriesError(null);
    try {
      let seriesId = selectedSeriesId;
      if (seriesMode === "new") {
        const created = await createDatasetSeries(newSeriesName.trim());
        seriesId = created.id;
        setSeriesList((prev) => [...prev, created]);
      }

      const uploaded = await uploadDataset(seriesFile, { seriesId, asOfDate });
      addDataset({
        id: uploaded.id,
        name: seriesFile.name,
        status: "profiling",
        row_count: null,
        column_count: null,
        error_message: null,
        series_id: seriesId,
        as_of_date: asOfDate,
        created_at: new Date().toISOString(),
      });
      setSelectedId(uploaded.id);

      setShowSeriesPanel(false);
      setSeriesFile(null);
      setNewSeriesName("");
      setSeriesMode("existing");
      setSelectedSeriesId(seriesId);
    } catch (err) {
      setSeriesError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setSeriesUploading(false);
    }
  };

  return (
    <div className="shell">
      <Sidebar />
      <div className="main">
        <Topbar
          selectedDatasetName={selectedDataset?.name ?? null}
          onUploadClick={handleTriggerUpload}
          uploading={uploading}
        />
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          style={{ display: "none" }}
          onChange={handleFileChange}
        />
        <div className="content">
          {uploadError && (
            <div className="card" style={{ marginBottom: 16, borderColor: "var(--bad)" }}>
              {uploadError}
            </div>
          )}

          <div style={{ marginBottom: 16 }}>
            <button
              type="button"
              className="btn ghost"
              onClick={() => setShowSeriesPanel((prev) => !prev)}
            >
              {showSeriesPanel ? "Cancel" : "+ Add to a recurring series"}
            </button>

            {showSeriesPanel && (
              <div className="card" style={{ marginTop: 10, maxWidth: 420, display: "flex", flexDirection: "column", gap: 10 }}>
                <p className="spec-caption">
                  For data that updates daily/weekly -- tag this upload into a named series so scoring can
                  always resolve to whatever's most recent.
                </p>

                {seriesMode === "existing" ? (
                  <select
                    className="spec-select"
                    value={selectedSeriesId}
                    onChange={(e) => setSelectedSeriesId(e.target.value)}
                  >
                    <option value="">Choose a series…</option>
                    {seriesList.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    className="search-input"
                    style={{ margin: 0 }}
                    placeholder="New series name (e.g. daily_case_counts)"
                    value={newSeriesName}
                    onChange={(e) => setNewSeriesName(e.target.value)}
                  />
                )}
                <button
                  type="button"
                  className="btn ghost"
                  style={{ alignSelf: "flex-start" }}
                  onClick={() => setSeriesMode((m) => (m === "existing" ? "new" : "existing"))}
                >
                  {seriesMode === "existing" ? "+ New series instead" : "Pick an existing series instead"}
                </button>

                <label className="spec-field">
                  <span className="spec-label">As-of date</span>
                  <input
                    type="date"
                    className="spec-select"
                    value={asOfDate}
                    onChange={(e) => setAsOfDate(e.target.value)}
                  />
                </label>

                <input
                  ref={seriesFileInputRef}
                  type="file"
                  accept=".csv"
                  onChange={(e) => setSeriesFile(e.target.files?.[0] ?? null)}
                />

                {seriesError && (
                  <p className="spec-caption" style={{ color: "var(--bad)" }}>
                    {seriesError}
                  </p>
                )}

                <button
                  type="button"
                  className="btn primary"
                  style={{ justifyContent: "center" }}
                  disabled={seriesUploading}
                  onClick={handleSeriesSubmit}
                >
                  {seriesUploading ? "Uploading…" : "Upload to series"}
                </button>
              </div>
            )}
          </div>

          <div className="body-grid">
            <DatasetList
              datasets={datasets}
              selectedId={selectedId}
              onSelect={setSelectedId}
              onTriggerUpload={handleTriggerUpload}
              uploading={uploading}
            />

            <div className="profile-col">
              {loading ? (
                <div className="empty-state">Loading datasets…</div>
              ) : error ? (
                <div className="empty-state">{error}</div>
              ) : !selectedDataset ? (
                <div className="empty-state">
                  Upload a CSV to see its auto-generated profile here.
                </div>
              ) : (
                <>
                  <div className="profile-head">
                    <div>
                      <h2 className="mono">{selectedDataset.name}</h2>
                      <div className="profile-meta">
                        {profile?.row_count ?? selectedDataset.row_count ?? "…"} rows ·{" "}
                        {profile?.column_count ?? selectedDataset.column_count ?? "…"} columns
                      </div>
                    </div>
                    {selectedDataset.status === "profiled" ? (
                      <span className="pill good">
                        <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                          <path
                            d="M3 8.5l3.2 3.2L13 4.5"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                        Profiled
                      </span>
                    ) : (
                      <StatusPill status={selectedDataset.status} />
                    )}
                  </div>

                  {selectedDataset.status === "error" ? (
                    <div className="card" style={{ borderColor: "var(--bad)", color: "var(--bad)" }}>
                      {selectedDataset.error_message ?? profile?.error_message ?? "Profiling failed."}
                    </div>
                  ) : (
                    <>
                      <div className="card cta-bar">
                        <span>Ready to build something with this data?</span>
                        <button
                          type="button"
                          className="btn primary"
                          onClick={() => navigate(`/datasets/${selectedDataset.id}/analysis`)}
                          disabled={profile?.status !== "profiled"}
                        >
                          Describe what you want to do →
                        </button>
                      </div>

                      <AiSummaryCard
                        aiDescription={profile?.ai_description ?? null}
                        pending={profile?.status !== "profiled"}
                      />

                      {profile?.columns && <ColumnProfileGrid columns={profile.columns} />}
                    </>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
