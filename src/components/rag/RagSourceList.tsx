import { useTranslation } from "react-i18next";

export interface Source {
  title: string;
  slug: string;
  chunk?: string;
  score?: number;
}

interface RagSourceListProps {
  sources: Source[];
}

export function RagSourceList({ sources }: RagSourceListProps) {
  const { t } = useTranslation();

  if (sources.length === 0) return null;

  return (
    <div>
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-2">
        {t("rag.sources")}
      </h2>
      <div className="space-y-2">
        {sources.map((src, i) => (
          <div
            key={i}
            className="bg-white border border-gray-200 rounded-lg px-4 py-3"
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-blue-700 truncate">
                {src.title}
              </span>
              {src.score !== undefined && (
                <span className="text-xs text-gray-400 shrink-0 ml-2">
                  {t("rag.score")}: {(src.score * 100).toFixed(0)}%
                </span>
              )}
            </div>
            <p className="text-xs text-gray-500 line-clamp-2">
              {src.chunk?.slice(0, 200)}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
