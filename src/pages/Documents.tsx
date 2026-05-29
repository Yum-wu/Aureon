import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDocuments } from "../hooks/useDocuments";
import { DocumentUpload } from "../components/documents/DocumentUpload";

const TYPE_BADGE: Record<string, string> = {
  md: "bg-green-100 text-green-700",
  pdf: "bg-red-100 text-red-700",
  txt: "bg-gray-100 text-gray-600",
};

export function Documents() {
  const { t } = useTranslation();
  const { documents, totalDocs, totalChunks, loading, error, refetch } = useDocuments();
  const [filter, setFilter] = useState("");
  const [showUpload, setShowUpload] = useState(false);

  const filtered = filter
    ? documents.filter(
        (d) =>
          d.title.toLowerCase().includes(filter.toLowerCase()) ||
          d.source.toLowerCase().includes(filter.toLowerCase())
      )
    : documents;

  // Error state
  if (error) {
    return (
      <div className="h-full overflow-y-auto px-4 md:px-6 py-4 md:py-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-4 md:mb-6 gap-4">
          <div>
            <h1 className="text-xl md:text-2xl font-bold text-gray-900">{t("documents.title")}</h1>
            <p className="text-sm text-gray-500 mt-1">{t("documents.subtitle")}</p>
          </div>
        </div>
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
          <p className="text-red-600 mb-4">{t("documents.error_loading")}</p>
          <p className="text-sm text-gray-500 mb-4">{error}</p>
          <button
            onClick={refetch}
            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
          >
            {t("documents.retry")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto px-4 md:px-6 py-4 md:py-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-4 md:mb-6 gap-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-gray-900">{t("documents.title")}</h1>
          <p className="text-sm text-gray-500 mt-1">{t("documents.subtitle")}</p>
        </div>
        <div className="flex items-center gap-4">
          <button
            onClick={() => setShowUpload((v) => !v)}
            className="px-4 py-2 rounded-lg bg-blue-500 text-white text-sm font-medium hover:bg-blue-600 transition-colors"
          >
            {showUpload ? t("documents.upload.upload_another") : t("documents.upload.button")}
          </button>
          <div className="text-right">
            <p className="text-xs text-gray-500">{t("documents.total_docs")}</p>
            <p className="text-xl font-bold text-gray-800">{totalDocs}</p>
          </div>
          <div className="text-right">
            <p className="text-xs text-gray-500">{t("documents.total_chunks")}</p>
            <p className="text-xl font-bold text-gray-800">{totalChunks}</p>
          </div>
        </div>
      </div>

      {/* Search bar */}
      <div className="mb-4">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={t("documents.search_placeholder")}
          className="w-full px-4 py-2 rounded-lg border border-gray-200 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </div>

      {/* Upload area */}
      {showUpload && (
        <div className="mb-4">
          <DocumentUpload onUploadSuccess={refetch} />
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="flex space-x-1.5">
            <span className="w-2.5 h-2.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
            <span className="w-2.5 h-2.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
            <span className="w-2.5 h-2.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
          </div>
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex items-center justify-center h-64 text-gray-400">
          <p>{t("documents.empty")}</p>
        </div>
      ) : (
        <>
          {/* Desktop: Table */}
          <div className="hidden md:block bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    {t("documents.table.name")}
                  </th>
                  <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    {t("documents.table.source")}
                  </th>
                  <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    {t("documents.table.type")}
                  </th>
                  <th className="text-right px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    {t("documents.table.chunks")}
                  </th>
                  <th className="text-center px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    {t("documents.table.status")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((doc, i) => (
                  <tr
                    key={`${doc.source}-${doc.title}-${i}`}
                    className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50 transition-colors"
                  >
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        <span className="text-lg">{doc.file_type === "pdf" ? "📄" : "📝"}</span>
                        <span className="text-sm font-medium text-gray-800 truncate max-w-[240px]">
                          {doc.title}
                        </span>
                      </div>
                    </td>
                    <td className="px-5 py-3.5 text-sm text-gray-500 truncate max-w-[160px]">
                      {doc.source}
                    </td>
                    <td className="px-5 py-3.5">
                      <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${TYPE_BADGE[doc.file_type] || TYPE_BADGE.txt}`}>
                        {doc.file_type.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-right text-sm font-medium text-gray-700">
                      {doc.chunk_count}
                    </td>
                    <td className="px-5 py-3.5 text-center">
                      <span className="inline-block w-2 h-2 rounded-full bg-green-500" title={t("documents.status.ready")} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile: Cards */}
          <div className="md:hidden space-y-3">
            {filtered.map((doc, i) => (
              <div key={`${doc.source}-${doc.title}-${i}`} className="bg-white rounded-xl border border-gray-100 shadow-sm p-4">
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-lg shrink-0">{doc.file_type === "pdf" ? "📄" : "📝"}</span>
                    <span className="text-sm font-medium text-gray-800 truncate">{doc.title}</span>
                  </div>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium shrink-0 ml-2 ${TYPE_BADGE[doc.file_type] || TYPE_BADGE.txt}`}>
                    {doc.file_type.toUpperCase()}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs text-gray-500">
                  <span className="truncate max-w-[120px]">{doc.source}</span>
                  <div className="flex items-center gap-3">
                    <span>{doc.chunk_count} 片段</span>
                    <span className="w-2 h-2 rounded-full bg-green-500" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
