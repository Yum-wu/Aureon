import { useState, useEffect } from "react";

interface BlogConfig {
  url: string;
  sync_enabled: boolean;
  last_synced: string | null;
}

export function useBlogConfig() {
  const [config, setConfig] = useState<BlogConfig | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchConfig() {
      try {
        const res = await fetch("/api/rag/blog/config");
        if (res.ok) {
          setConfig(await res.json());
        }
      } catch {
        setConfig({ url: "", sync_enabled: false, last_synced: null });
      } finally {
        setLoading(false);
      }
    }

    fetchConfig();
  }, []);

  return { config, loading };
}
