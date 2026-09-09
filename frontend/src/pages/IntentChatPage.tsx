import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getDataset, getProfile, listDatasets } from "../api/datasets";
import {
  addJoinDataset,
  createModelingSpec,
  getModelingSpec,
  listJoinDatasets,
  removeJoinDataset,
  sendChatMessage,
  updateModelingSpec,
} from "../api/modelingSpecs";
import { getModelForSpec } from "../api/models";
import { ChatBubble } from "../components/ChatBubble";
import { ChatComposer } from "../components/ChatComposer";
import { DatasetListItem } from "../components/DatasetListItem";
import { Sidebar } from "../components/Sidebar";
import { SpecCard } from "../components/SpecCard";
import type {
  Cadence,
  ChatMessage,
  ColumnProfile,
  Dataset,
  DatasetProfile,
  JoinDataset,
  JoinType,
  ModelingSpec,
} from "../types";

function mergeAvailableColumns(
  baseColumns: ColumnProfile[],
  joins: JoinDataset[],
  profilesByDataset: Map<string, DatasetProfile>,
): ColumnProfile[] {
  // Mirrors training_data.py's ambiguous-column-collision rule: any column
  // name appearing in more than one attached dataset (base included) is
  // left out of the pickable pool entirely, rather than guessing which
  // dataset's copy a user meant.
  const nameCounts = new Map<string, number>();
  for (const c of baseColumns) nameCounts.set(c.name, (nameCounts.get(c.name) ?? 0) + 1);

  const joinColumnSets = joins.map((jd) => {
    const profile = profilesByDataset.get(jd.dataset_id);
    const columns = profile?.columns?.filter((c) => c.name !== jd.join_key_column) ?? [];
    for (const c of columns) nameCounts.set(c.name, (nameCounts.get(c.name) ?? 0) + 1);
    return columns;
  });

  const isUnique = (name: string) => (nameCounts.get(name) ?? 0) <= 1;
  const merged = baseColumns.filter((c) => isUnique(c.name));
  for (const columns of joinColumnSets) {
    merged.push(...columns.filter((c) => isUnique(c.name)));
  }
  return merged;
}

export function IntentChatPage() {
  const { datasetId, specId } = useParams<{ datasetId: string; specId?: string }>();
  const navigate = useNavigate();

  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [profile, setProfile] = useState<DatasetProfile | null>(null);
  const [spec, setSpec] = useState<ModelingSpec | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [allDatasets, setAllDatasets] = useState<Dataset[]>([]);
  const [joinDatasets, setJoinDatasets] = useState<JoinDataset[]>([]);
  const [profilesByDataset, setProfilesByDataset] = useState<Map<string, DatasetProfile>>(new Map());
  const [existingModelId, setExistingModelId] = useState<string | null>(null);

  useEffect(() => {
    if (!datasetId) return;
    getDataset(datasetId).then(setDataset).catch(() => {});
    getProfile(datasetId).then(setProfile).catch(() => {});
  }, [datasetId]);

  useEffect(() => {
    listDatasets().then(setAllDatasets).catch(() => {});
  }, []);

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

  useEffect(() => {
    if (!specId) {
      setJoinDatasets([]);
      setExistingModelId(null);
      return;
    }
    listJoinDatasets(specId).then(setJoinDatasets).catch(() => {});
    getModelForSpec(specId)
      .then((model) => setExistingModelId(model.id))
      .catch(() => setExistingModelId(null));
  }, [specId]);

  // Proactively fetch a profile for every attached join dataset (not just
  // the one currently being configured in the attach form) so the merged
  // feature picker stays accurate. profilesByDataset is intentionally not
  // a dependency -- re-running on every cache update would refetch nothing
  // new but would re-run this effect in a loop; each join dataset only
  // needs fetching once.
  useEffect(() => {
    joinDatasets.forEach((jd) => {
      setProfilesByDataset((prev) => {
        if (prev.has(jd.dataset_id)) return prev;
        getProfile(jd.dataset_id)
          .then((p) => setProfilesByDataset((cur) => new Map(cur).set(jd.dataset_id, p)))
          .catch(() => {});
        return prev;
      });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [joinDatasets]);

  const getProfileForDataset = useCallback(
    async (id: string): Promise<DatasetProfile> => {
      const cached = profilesByDataset.get(id);
      if (cached) return cached;
      const fetched = await getProfile(id);
      setProfilesByDataset((prev) => new Map(prev).set(id, fetched));
      return fetched;
    },
    [profilesByDataset],
  );

  const attachableDatasets = useMemo(() => {
    const attachedIds = new Set(joinDatasets.map((j) => j.dataset_id));
    return allDatasets.filter(
      (d) => d.status === "profiled" && d.id !== datasetId && !attachedIds.has(d.id),
    );
  }, [allDatasets, joinDatasets, datasetId]);

  const availableColumns = useMemo(
    () => mergeAvailableColumns(profile?.columns ?? [], joinDatasets, profilesByDataset),
    [profile, joinDatasets, profilesByDataset],
  );

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
    acknowledge_imbalance?: boolean;
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

  const handleAttachDataset = async (targetDatasetId: string, joinKeyColumn: string, joinType: JoinType) => {
    if (!specId) return;
    const created = await addJoinDataset(specId, {
      dataset_id: targetDatasetId,
      join_key_column: joinKeyColumn,
      join_type: joinType,
    });
    setJoinDatasets((prev) => [...prev, created]);
  };

  const handleDetachDataset = async (joinId: string) => {
    if (!specId) return;
    await removeJoinDataset(specId, joinId);
    setJoinDatasets((prev) => prev.filter((j) => j.id !== joinId));
  };

  return (
    <div className="shell">
      <Sidebar activeItem="new-analysis" />
      <div className="main">
        <div className="topbar">
          <div className="breadcrumb">
            <Link to="/">New Analysis</Link>
            {dataset ? <> / <b className="mono">{dataset.name}</b></> : null}
          </div>
        </div>
        <div className="content">
          {!datasetId ? (
            <div style={{ maxWidth: 480 }}>
              <p className="panel-title">Choose a dataset to analyze</p>
              <div className="ds-list">
                {allDatasets.filter((d) => d.status === "profiled").length === 0 ? (
                  <div className="empty-state">
                    No profiled datasets yet -- upload one from the Datasets page first.
                  </div>
                ) : (
                  allDatasets
                    .filter((d) => d.status === "profiled")
                    .map((d) => (
                      <DatasetListItem
                        key={d.id}
                        dataset={d}
                        selected={false}
                        onSelect={(id) => navigate(`/datasets/${id}/analysis`)}
                      />
                    ))
                )}
              </div>
            </div>
          ) : loadError ? (
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
                availableColumns={availableColumns}
                onPatch={handlePatch}
                disabled={sending}
                baseDatasetName={dataset?.name ?? ""}
                baseColumns={profile?.columns ?? []}
                joinDatasets={joinDatasets}
                attachableDatasets={attachableDatasets}
                getProfileForDataset={getProfileForDataset}
                onAttachDataset={handleAttachDataset}
                onDetachDataset={handleDetachDataset}
                existingModelId={existingModelId}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
