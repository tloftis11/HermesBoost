import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  createDataAcquisitionSession,
  getDataAcquisitionSession,
  sendDataAcquisitionMessage,
} from "../api/dataAcquisition";
import { confirmDataset, deleteDataset } from "../api/datasets";
import { ChatBubble } from "../components/ChatBubble";
import { ChatComposer } from "../components/ChatComposer";
import { Sidebar } from "../components/Sidebar";
import type { DataAcquisitionMessage } from "../types";

export function DataAcquisitionPage() {
  const { sessionId } = useParams<{ sessionId?: string }>();
  const navigate = useNavigate();

  const [messages, setMessages] = useState<DataAcquisitionMessage[]>([]);
  const [problemDescription, setProblemDescription] = useState("");
  const [starting, setStarting] = useState(false);
  const [sending, setSending] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [confirmedIds, setConfirmedIds] = useState<Set<string>>(new Set());
  const [discardedIds, setDiscardedIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!sessionId) return;
    getDataAcquisitionSession(sessionId)
      .then((detail) => setMessages(detail.messages))
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Could not load session"));
  }, [sessionId]);

  const handleStart = async () => {
    if (!problemDescription.trim()) return;
    setStarting(true);
    setLoadError(null);
    try {
      const created = await createDataAcquisitionSession(problemDescription.trim());
      navigate(`/data-acquisition/${created.session.id}`, { replace: true });
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Could not start session");
    } finally {
      setStarting(false);
    }
  };

  const handleSend = async (message: string) => {
    if (!sessionId) return;
    setMessages((prev) => [
      ...prev,
      { role: "user", display_text: message, staged_dataset_ids: [], created_at: new Date().toISOString() },
    ]);
    setSending(true);
    try {
      const resp = await sendDataAcquisitionMessage(sessionId, message);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          display_text: resp.reply_message,
          staged_dataset_ids: resp.staged_dataset_ids,
          created_at: new Date().toISOString(),
        },
      ]);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSending(false);
    }
  };

  const handleConfirm = async (datasetId: string) => {
    try {
      await confirmDataset(datasetId);
      setConfirmedIds((prev) => new Set(prev).add(datasetId));
    } catch {
      // leave state as-is on failure
    }
  };

  const handleDiscard = async (datasetId: string) => {
    try {
      await deleteDataset(datasetId);
      setDiscardedIds((prev) => new Set(prev).add(datasetId));
    } catch {
      // leave state as-is on failure
    }
  };

  const allStagedIds = messages.flatMap((m) => m.staged_dataset_ids);

  return (
    <div className="shell">
      <Sidebar />
      <div className="main">
        <div className="topbar">
          <div className="breadcrumb">Not sure what data you need?</div>
        </div>
        <div className="content">
          {!sessionId ? (
            <div className="card" style={{ maxWidth: 640 }}>
              <h3>Describe what you're trying to do</h3>
              <p className="spec-caption">
                Tell HermesBoost the problem you want to model. It'll search for real public data
                sources, preview candidates, and stage anything promising for you to review --
                nothing becomes a usable dataset until you confirm it.
              </p>
              <textarea
                className="spec-select"
                style={{ minHeight: 100, marginTop: 12 }}
                placeholder="e.g. I want to predict which counties are at risk of a measles outbreak"
                value={problemDescription}
                onChange={(e) => setProblemDescription(e.target.value)}
              />
              <button
                type="button"
                className="btn primary"
                style={{ marginTop: 12 }}
                disabled={starting || !problemDescription.trim()}
                onClick={handleStart}
              >
                {starting ? "Starting…" : "Start"}
              </button>
              {loadError && (
                <p className="spec-caption" style={{ color: "var(--bad)", marginTop: 8 }}>
                  {loadError}
                </p>
              )}
            </div>
          ) : (
            <>
              <div className="chat-list">
                {messages.map((m, i) => (
                  <div key={i}>
                    <ChatBubble
                      message={{ role: m.role, content: m.display_text, created_at: m.created_at }}
                    />
                    {m.staged_dataset_ids.map((datasetId) => (
                      <div
                        className="card"
                        key={datasetId}
                        style={{ maxWidth: 420, marginTop: 8, marginBottom: 8 }}
                      >
                        {discardedIds.has(datasetId) ? (
                          <p className="spec-caption">Discarded.</p>
                        ) : confirmedIds.has(datasetId) ? (
                          <p className="spec-caption" style={{ color: "var(--good)" }}>
                            Confirmed -- now profiling.
                          </p>
                        ) : (
                          <>
                            <p className="spec-caption">Staged a dataset for your review.</p>
                            <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                              <button
                                type="button"
                                className="btn primary"
                                onClick={() => handleConfirm(datasetId)}
                              >
                                Confirm
                              </button>
                              <button
                                type="button"
                                className="btn ghost"
                                onClick={() => handleDiscard(datasetId)}
                              >
                                Discard
                              </button>
                            </div>
                          </>
                        )}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
              <ChatComposer onSend={handleSend} disabled={sending} />
              {loadError && (
                <p className="spec-caption" style={{ color: "var(--bad)", marginTop: 8 }}>
                  {loadError}
                </p>
              )}
              {allStagedIds.length === 0 && messages.length > 0 && (
                <p className="spec-caption" style={{ marginTop: 8 }}>
                  Nothing staged yet -- keep describing what you need, or ask it to search for
                  something specific.
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
