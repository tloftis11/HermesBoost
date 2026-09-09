import { useEffect, useRef, useState } from "react";
import { getProfile } from "../api/datasets";
import type { DatasetProfile } from "../types";

const POLL_INTERVAL_MS = 2000;

export function useDatasetProfile(datasetId: string | null) {
  const [profile, setProfile] = useState<DatasetProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    setProfile(null);
    if (intervalRef.current !== null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (!datasetId) {
      return;
    }

    let cancelled = false;
    setLoading(true);

    const fetchOnce = async () => {
      try {
        const data = await getProfile(datasetId);
        if (cancelled) return;
        setProfile(data);
        setLoading(false);
        if (data.status !== "profiling" && intervalRef.current !== null) {
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
  }, [datasetId]);

  return { profile, loading };
}
