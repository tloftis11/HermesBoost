import { useEffect, useRef, useState } from "react";
import { getModel } from "../api/models";
import type { ModelGuided } from "../types";

const POLL_INTERVAL_MS = 2000;

export function useModelRun(modelId: string | null) {
  const [model, setModel] = useState<ModelGuided | null>(null);
  const [loading, setLoading] = useState(false);
  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    setModel(null);
    if (intervalRef.current !== null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (!modelId) {
      return;
    }

    let cancelled = false;
    setLoading(true);

    const fetchOnce = async () => {
      try {
        const data = await getModel(modelId);
        if (cancelled) return;
        setModel(data);
        setLoading(false);
        if (data.status !== "training" && intervalRef.current !== null) {
          window.clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      } catch {
        if (!cancelled) setLoading(false);
      }
    };

    fetchOnce();
    intervalRef.current = window.setInterval(fetchOnce, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      if (intervalRef.current !== null) {
        window.clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [modelId]);

  return { model, loading };
}
