import { useState } from "react";
import { useTranslation } from "react-i18next";

interface RagQueryFormProps {
  query: string;
  onQueryChange: (q: string) => void;
  loading: boolean;
  onSubmit: () => void;
}

export function RagQueryForm({
  query,
  onQueryChange,
  loading,
  onSubmit,
}: RagQueryFormProps) {
  const { t } = useTranslation();

  // Search history (localStorage)
  const [history, setHistory] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem("aureon_search_history") || "[]");
    } catch {
      return [];
    }
  });

  const saveToHistory = (q: string) => {
    const updated = [q, ...history.filter((h) => h !== q)].slice(0, 10);
    setHistory(updated);
    localStorage.setItem("aureon_search_history", JSON.stringify(updated));
  };

  // Expose saveToHistory to parent via onSubmit wrapper
  const handleSubmit = () => {
    const trimmed = query.trim();
    if (!trimmed || loading) return;
    saveToHistory(trimmed);
    onSubmit();
  };

  return (
    <div className="bg-white border-b border-gray-200 px-6 py-4">
      <div className="flex gap-3 max-w-3xl">
        <input
          type="text"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !loading) handleSubmit();
          }}
          placeholder={t("rag.inputPlaceholder")}
          className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
          disabled={loading}
        />
        <button
          onClick={handleSubmit}
          disabled={loading || !query.trim()}
          className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shrink-0"
        >
          {loading ? "...stream" : t("rag.ask")}
        </button>
      </div>
      {/* Example queries */}
      <div className="flex gap-2 mt-3 flex-wrap">
        {(t("rag.examples", { returnObjects: true }) as string[]).map(
          (ex: string) => (
            <button
              key={ex}
              onClick={() => onQueryChange(ex)}
              className="text-xs px-2.5 py-1 rounded-full bg-gray-100 text-gray-500 hover:bg-gray-200 hover:text-gray-700 transition-colors"
            >
              {ex}
            </button>
          ),
        )}
      </div>
      {/* Search history */}
      {history.length > 0 && !loading && (
        <div className="mt-3">
          <p className="text-xs text-gray-400 mb-1.5">{t("search.history")}</p>
          <div className="flex gap-2 flex-wrap">
            {history.slice(0, 5).map((h) => (
              <button
                key={h}
                onClick={() => onQueryChange(h)}
                className="text-xs px-2.5 py-1 rounded-full bg-blue-50 text-blue-600 hover:bg-blue-100 transition-colors"
              >
                {h.length > 30 ? h.slice(0, 30) + "бн" : h}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
