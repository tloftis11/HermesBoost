import { useCallback, useEffect, useState } from "react";
import { listDatasets } from "../api/datasets";
import type { Dataset } from "../types";

export function useDatasets() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await listDatasets();
      setDatasets(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load datasets");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const addDataset = useCallback((dataset: Dataset) => {
    setDatasets((prev) => [dataset, ...prev]);
  }, []);

  return { datasets, loading, error, refresh, addDataset };
}
