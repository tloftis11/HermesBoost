import { useEffect, useState } from "react";
import { createApiKey, listApiKeys, revokeApiKey } from "../api/apiKeys";
import { Sidebar } from "../components/Sidebar";
import type { ApiKeyCreated, ApiKeyOut } from "../types";

function formatDateTime(iso: string | null): string {
  if (!iso) return "--";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function SettingsPage() {
  const [keys, setKeys] = useState<ApiKeyOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [newKeyName, setNewKeyName] = useState("");
  const [creating, setCreating] = useState(false);
  const [justCreated, setJustCreated] = useState<ApiKeyCreated | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => {
    listApiKeys()
      .then(setKeys)
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load API keys"))
      .finally(() => setLoading(false));
  };

  useEffect(refresh, []);

  const handleCreate = async () => {
    if (!newKeyName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const created = await createApiKey(newKeyName.trim());
      setJustCreated(created);
      setNewKeyName("");
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create API key");
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (id: string) => {
    try {
      await revokeApiKey(id);
      refresh();
    } catch {
      // leave the list as-is on failure
    }
  };

  return (
    <div className="shell">
      <Sidebar activeItem="settings" />
      <div className="main">
        <div className="topbar">
          <div className="breadcrumb">Settings</div>
        </div>
        <div className="content">
          <div className="card" style={{ maxWidth: 640, marginBottom: 16 }}>
            <h3>API Keys</h3>
            <p className="spec-caption">
              Use an API key to pull model scores from outside HermesBoost -- send it as an{" "}
              <code>X-API-Key</code> header. Keys are scoped to your organization and can be revoked
              anytime.
            </p>

            {justCreated && (
              <div
                className="card"
                style={{ marginTop: 12, background: "var(--accent-soft)", borderColor: "var(--accent)" }}
              >
                <p className="spec-caption" style={{ color: "var(--ink)", fontWeight: 700 }}>
                  Copy this key now -- it won't be shown again.
                </p>
                <div className="spec-value mono" style={{ userSelect: "all", wordBreak: "break-all" }}>
                  {justCreated.raw_key}
                </div>
                <button
                  type="button"
                  className="btn ghost"
                  style={{ marginTop: 8 }}
                  onClick={() => setJustCreated(null)}
                >
                  Done
                </button>
              </div>
            )}

            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <input
                className="search-input"
                style={{ margin: 0, flex: 1 }}
                placeholder="Key name (e.g. BI pipeline)"
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
              />
              <button
                type="button"
                className="btn primary"
                disabled={creating || !newKeyName.trim()}
                onClick={handleCreate}
              >
                {creating ? "Creating…" : "+ Create key"}
              </button>
            </div>

            {error && (
              <p className="spec-caption" style={{ color: "var(--bad)", marginTop: 8 }}>
                {error}
              </p>
            )}
          </div>

          {loading ? (
            <div className="empty-state">Loading API keys…</div>
          ) : keys.length === 0 ? (
            <div className="empty-state">No API keys yet.</div>
          ) : (
            <div className="ds-list" style={{ maxWidth: 640 }}>
              {keys.map((k) => (
                <div className="ds-item" key={k.id} style={{ cursor: "default" }}>
                  <div className="ds-head">
                    <span className="ds-name">{k.name}</span>
                    {k.revoked_at ? (
                      <span className="pill bad">Revoked</span>
                    ) : (
                      <button type="button" className="btn ghost" onClick={() => handleRevoke(k.id)}>
                        Revoke
                      </button>
                    )}
                  </div>
                  <div className="ds-meta mono">{k.key_prefix}…</div>
                  <div className="ds-meta">
                    Created {formatDateTime(k.created_at)} · Last used {formatDateTime(k.last_used_at)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
