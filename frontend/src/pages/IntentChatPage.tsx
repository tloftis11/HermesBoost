import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getDataset, getProfile } from "../api/datasets";
import { createModelingSpec, getModelingSpec, sendChatMessage, updateModelingSpec } from "../api/modelingSpecs";
import { ChatBubble } from "../components/ChatBubble";
import { ChatComposer } from "../components/ChatComposer";
import { Sidebar } from "../components/Sidebar";
import { SpecCard } from "../components/SpecCard";
import type { Cadence, ChatMessage, Dataset, DatasetProfile, ModelingSpec } from "../types";

export function IntentChatPage() {
  const { datasetId, specId } = useParams<{ datasetId: string; specId?: string }>();
  const navigate = useNavigate();

  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [profile, setProfile] = useState<DatasetProfile | null>(null);
  const [spec, setSpec] = useState<ModelingSpec | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!datasetId) return;
    getDataset(datasetId).then(setDataset).catch(() => {});
    getProfile(datasetId).then(setProfile).catch(() => {});
  }, [datasetId]);

  useEffect(() => {
    if (!datasetId) return;
    let cancelled = false;

    async function init() {
      if (!specId) {
        try {
          const created = await createModelingSpec(datasetId!);
          if (!cancelled) navigate(`/datasets/${datasetId}/analysis/${created.id}`, { replace: true });
        } catch (err) {
          if (!cancelled) setLoadError(err instanceof Error ? err.message : "Could not start analysis");
        }
        return;
      }
      try {
        const detail = await getModelingSpec(specId);
        if (!cancelled) {
          setSpec(detail.spec);
          setMessages(detail.messages);
        }
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : "Could not load analysis");
      }
    }

    init();
    return () => {
      cancelled = true;
    };
  }, [datasetId, specId, navigate]);

  const handleSend = async (message: string) => {
    if (!specId) return;
    const now = new Date().toISOString();
    setMessages((prev) => [...prev, { role: "user", content: message, created_at: now }]);
    setSending(true);
    try {
      const result = await sendChatMessage(specId, message);
      setSpec(result.spec);
      setMessages((prev) => [...prev, { role: "assistant", content: result.reply_message, created_at: new Date().toISOString() }]);
    } catch (err) {
      const detail = err instanceof Error ? err.message : "unknown error";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Something went wrong: ${detail}`, created_at: new Date().toISOString() },
      ]);
    } finally {
      setSending(false);
    }
  };

  const handlePatch = async (patch: {
    candidate_features?: string[];
    retrain_cadence?: Cadence;
    score_cadence?: Cadence;
  }) => {
    if (!specId) return;
    try {
      const updated = await updateModelingSpec(specId, patch);
      setSpec(updated);
    } catch {
      // leave spec state as-is on failure -- no destructive local overwrite
    }
  };

  return (
    <div className="shell">
      <Sidebar activeItem="new-analysis" />
      <div className="main">
        <div className="topbar">
          <div className="breadcrumb">
            New Analysis{dataset ? <> / <b className="mono">{dataset.name}</b></> : null}
          </div>
        </div>
        <div className="content">
          {loadError ? (
            <div className="card" style={{ borderColor: "var(--bad)", color: "var(--bad)" }}>
              {loadError}
            </div>
          ) : !spec ? (
            <div className="empty-state">Starting analysis…</div>
          ) : (
            <div className="chat-grid">
              <div className="chat-col">
                <div className="transcript">
                  {messages.length === 0 ? (
                    <div className="empty-transcript">Describe what you want to do with this dataset.</div>
                  ) : (
                    messages.map((m, i) => <ChatBubble key={i} message={m} />)
                  )}
                </div>
                <ChatComposer onSend={handleSend} disabled={sending} />
              </div>

              <SpecCard
                spec={spec}
                availableColumns={profile?.columns ?? []}
                onPatch={handlePatch}
                disabled={sending}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
