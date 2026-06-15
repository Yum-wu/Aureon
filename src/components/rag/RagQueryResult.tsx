import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { RagSourceList, type Source } from "./RagSourceList";

interface RagQueryResultProps {
  answer: string;
  sources: Source[];
  loading: boolean;
  error: string | null;
}

export function RagQueryResult({
  answer,
  sources,
  loading,
  error,
}: RagQueryResultProps) {
  const { t } = useTranslation();

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4">
      {!answer && !loading && !error && (
        <div className="flex items-center justify-center h-full text-gray-400">
          <div className="text-center">
            <div className="text-5xl mb-4">?</div>
            <p className="text-base">{t("rag.noQuery")}</p>
          </div>
        </div>
      )}

      {loading && !answer && (
        <div className="flex items-center justify-center h-full">
          <div className="text-center">
            <div className="flex justify-center space-x-1.5 mb-4">
              <span
                className="w-2.5 h-2.5 bg-blue-400 rounded-full animate-bounce"
                style={{ animationDelay: "0ms" }}
              />
              <span
                className="w-2.5 h-2.5 bg-blue-400 rounded-full animate-bounce"
                style={{ animationDelay: "150ms" }}
              />
              <span
                className="w-2.5 h-2.5 bg-blue-400 rounded-full animate-bounce"
                style={{ animationDelay: "300ms" }}
              />
            </div>
            <p className="text-sm text-gray-400">{t("rag.asking")}</p>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
          ?? {error}
          <p className="text-xs text-red-500 mt-1">{t("rag.error")}</p>
        </div>
      )}

      {(answer || (loading && answer)) && (
        <div className="space-y-6 max-w-3xl">
          {/* Answer */}
          <div className="bg-white border border-gray-200 rounded-xl px-5 py-4">
            <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-2">
              Answer
            </h2>
            <div className="prose prose-sm max-w-none text-gray-800">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {answer}
              </ReactMarkdown>
            </div>
            {loading && (
              <span className="inline-block w-2 h-4 bg-blue-500 ml-1 animate-pulse" />
            )}
          </div>

          {/* Sources */}
          <RagSourceList sources={sources} />
        </div>
      )}
    </div>
  );
}
