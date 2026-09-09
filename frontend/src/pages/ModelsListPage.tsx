import { useMemo, useState } from "react";
import { ModelListItem } from "../components/ModelListItem";
import { Sidebar } from "../components/Sidebar";
import { useModels } from "../hooks/useModels";

export function ModelsListPage() {
  const { models, loading, error } = useModels();
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return models;
    return models.filter(
      (m) =>
        (m.task_description ?? "").toLowerCase().includes(q) ||
        m.dataset_name.toLowerCase().includes(q),
    );
  }, [models, query]);

  return (
    <div className="shell">
      <Sidebar activeItem="models" />
      <div className="main">
        <div className="topbar">
          <div className="breadcrumb">Models</div>
        </div>
        <div className="content">
          {loading ? (
            <div className="empty-state">Loading models…</div>
          ) : error ? (
            <div className="empty-state">{error}</div>
          ) : (
            <>
              <p className="panel-title">
                Your models <span>{models.length}</span>
              </p>
              <input
                className="search-input"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search models"
              />
              <div className="ds-list" style={{ marginTop: 12, maxWidth: 640 }}>
                {filtered.length === 0 ? (
                  <div className="empty-state">
                    {models.length === 0
                      ? "No models yet — build one from a dataset's analysis."
                      : "No matches."}
                  </div>
                ) : (
                  filtered.map((model) => <ModelListItem key={model.id} model={model} />)
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
