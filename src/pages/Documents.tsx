import { useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { authFetch } from "../services/authFetch";
import { useDocumentsQuery } from "../hooks/useDocumentsQuery";
import { useDeleteDocument } from "../hooks/useDeleteDocument";
import { useBlogConfig } from "../hooks/useBlogConfig";
import { DocumentUpload } from "../components/documents/DocumentUpload";
import { ConfirmDialog } from "../components/admin/ConfirmDialog";
import { FileText, BookOpen, BarChart3, Trash2, ChevronLeft, ChevronRight } from "lucide-react";
import { Breadcrumb } from "../components/ui/Breadcrumb";

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];
const DEFAULT_PAGE_SIZE = 20;

const TYPE_BADGE: Record<string, string> = {
  md: "bg-green-100 text-green-700",
  pdf: "bg-red-100 text-red-700",
  txt: "bg-[var(--bg-tertiary)] text-[var(--text-secondary)]",
  docx: "bg-blue-100 text-blue-700",
  xlsx: "bg-emerald-100 text-emerald-700",
};

export function Documents() {
  const { t } = useTranslation();
  const { data, isLoading, error, refetch } = useDocumentsQuery();
  const { config: blogConfig } = useBlogConfig();
  const deleteDocument = useDeleteDocument();
  const [showUpload, setShowUpload] = useState(false);
  const [filter, setFilter] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<{ source: string; title: string; chunkCount: number } | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  const documents = useMemo(() => data?.documents ?? [], [data]);
  const totalDocs = data?.totalDocs ?? 0;
  const totalChunks = data?.totalChunks ?? 0;

  const filtered = useMemo(() => {
    if (!filter) return documents;
    const lowerFilter = filter.toLowerCase();
    return documents.filter(
      (d) =>
        d.title.toLowerCase().includes(lowerFilter) ||
        d.source.toLowerCase().includes(lowerFilter)
    );
  }, [documents, filter]);

  // 分页计算
  const totalPages = Math.ceil(filtered.length / pageSize);
  const paginatedDocuments = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, page, pageSize]);

  // 页码变化时重置到第一页
  const handleFilterChange = (value: string) => {
    setFilter(value);
    setPage(1);
  };

  // Error state
  if (error) {
    return (
      <div className="h-full overflow-y-auto px-4 md:px-6 py-4 md:py-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-4 md:mb-6 gap-4">
          <div>
            <h1 className="text-xl md:text-2xl font-bold text-[var(--text-primary)]">{t("documents.title")}</h1>
            <p className="text-sm text-[var(--text-tertiary)] mt-1">{t("documents.subtitle")}</p>
          </div>
        </div>
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
          <p className="text-red-600 mb-4">{t("documents.error_loading")}</p>
          <p className="text-sm text-[var(--text-tertiary)] mb-4">{error instanceof Error ? error.message : String(error)}</p>
          <button
            onClick={() => refetch()}
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
      <Breadcrumb auto />
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-4 md:mb-6 gap-4 mt-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-[var(--text-primary)]">{t("documents.title")}</h1>
          <p className="text-sm text-[var(--text-tertiary)] mt-1">{t("documents.subtitle")}</p>
        </div>
        <div className="flex items-center gap-4">
          {/* Blog link */}
          {blogConfig?.url && (
            <a
              href={blogConfig.url}
              target="_blank"
              rel="noopener noreferrer"
              className="px-4 py-2 rounded-lg bg-[var(--bg-tertiary)] text-[var(--text-secondary)] text-sm font-medium hover:bg-[var(--bg-tertiary)] transition-colors flex items-center gap-2"
            >
              <span>{t('documents.open_blog')}</span>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
          )}

          {/* Sync blog button */}
          {blogConfig?.sync_enabled && (
            <button
              onClick={async () => {
                const res = await authFetch("/api/rag/blog/sync", { method: "POST" });
                if (res.ok) {
                  refetch();
                }
              }}
              className="px-4 py-2 rounded-lg bg-purple-500 text-white text-sm font-medium hover:bg-purple-600 transition-colors flex items-center gap-2"
            >
              <span>{t('documents.sync_blog')}</span>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          )}

          {/* Upload button */}
          <div data-onboarding="documents-upload">
            <button
              onClick={() => setShowUpload((v) => !v)}
              className="px-4 py-2 rounded-lg bg-blue-500 text-white text-sm font-medium hover:bg-blue-600 transition-colors"
            >
              {showUpload ? t("documents.upload.upload_another") : t("documents.upload.button")}
            </button>
          </div>
          <div className="text-right">
            <p className="text-xs text-[var(--text-tertiary)]">{t("documents.total_docs")}</p>
            <p className="text-xl font-bold text-[var(--text-primary)]">{totalDocs}</p>
          </div>
          <div className="text-right">
            <p className="text-xs text-[var(--text-tertiary)]">{t("documents.total_chunks")}</p>
            <p className="text-xl font-bold text-[var(--text-primary)]">{totalChunks}</p>
          </div>
        </div>
      </div>

      {/* Search bar */}
      <div className="mb-4">
        <input
          type="text"
          value={filter}
          onChange={(e) => handleFilterChange(e.target.value)}
          placeholder={t("documents.search_placeholder")}
          className="w-full px-4 py-2 rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </div>

      {/* Upload area */}
      {showUpload && (
        <div className="mb-4">
          <DocumentUpload onUploadSuccess={() => refetch()} />
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <div className="flex space-x-1.5">
            <span className="w-2.5 h-2.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
            <span className="w-2.5 h-2.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
            <span className="w-2.5 h-2.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
          </div>
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex items-center justify-center h-64 text-[var(--text-tertiary)]">
          <p>{t("documents.empty")}</p>
        </div>
      ) : (
        <>
          {/* Desktop: Table */}
          <div className="hidden md:block bg-[var(--bg-secondary)] rounded-xl border border-[var(--border)] shadow-sm overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  <th className="text-left px-5 py-3 text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wide">
                    {t("documents.table.name")}
                  </th>
                  <th className="text-left px-5 py-3 text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wide">
                    {t("documents.table.source")}
                  </th>
                  <th className="text-left px-5 py-3 text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wide">
                    {t("documents.table.type")}
                  </th>
                  <th className="text-right px-5 py-3 text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wide">
                    {t("documents.table.chunks")}
                  </th>
                  <th className="text-center px-5 py-3 text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wide">
                    {t("documents.table.status")}
                  </th>
                  <th className="text-center px-5 py-3 text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wide">
                    {t("documents.table.actions", "操作")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {paginatedDocuments.map((doc, i) => (
                  <tr
                    key={`${doc.source}-${doc.title}-${i}`}
                    className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--surface-inset)] transition-colors"
                  >
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        <span className="text-lg">{doc.file_type === "pdf" ? <FileText size={18} /> : doc.file_type === "docx" ? <BookOpen size={18} /> : doc.file_type === "xlsx" ? <BarChart3 size={18} /> : <FileText size={18} />}</span>
                        <span className="text-sm font-medium text-[var(--text-primary)] truncate max-w-[240px]">
                          {doc.title}
                        </span>
                      </div>
                    </td>
                    <td className="px-5 py-3.5 text-sm text-[var(--text-tertiary)] truncate max-w-[160px]">
                      {doc.source}
                    </td>
                    <td className="px-5 py-3.5">
                      <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${TYPE_BADGE[doc.file_type] || TYPE_BADGE.txt}`}>
                        {doc.file_type.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-right text-sm font-medium text-[var(--text-secondary)]">
                      {doc.chunk_count}
                    </td>
                    <td className="px-5 py-3.5 text-center">
                      <span className="inline-block w-2 h-2 rounded-full bg-green-500" title={t("documents.status.ready")} />
                    </td>
                    <td className="px-5 py-3.5 text-center">
                      <button
                        onClick={() => setDeleteTarget({ source: doc.source, title: doc.title, chunkCount: doc.chunk_count })}
                        className="inline-flex items-center gap-1 px-2 py-1 text-xs text-[var(--error)] hover:bg-red-500/10 rounded transition-colors"
                        title={t("documents.delete.tooltip", "删除此文档")}
                      >
                        <Trash2 size={14} />
                        <span>{t("documents.delete.button", "删除")}</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile: Cards */}
          <div className="md:hidden space-y-3">
            {paginatedDocuments.map((doc, i) => (
              <div key={`${doc.source}-${doc.title}-${i}`} className="bg-[var(--bg-secondary)] rounded-xl border border-[var(--border)] shadow-sm p-4">
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-lg shrink-0">{doc.file_type === "pdf" ? <FileText size={18} /> : doc.file_type === "docx" ? <BookOpen size={18} /> : doc.file_type === "xlsx" ? <BarChart3 size={18} /> : <FileText size={18} />}</span>
                    <span className="text-sm font-medium text-[var(--text-primary)] truncate">{doc.title}</span>
                  </div>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium shrink-0 ml-2 ${TYPE_BADGE[doc.file_type] || TYPE_BADGE.txt}`}>
                    {doc.file_type.toUpperCase()}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs text-[var(--text-tertiary)]">
                  <span className="truncate max-w-[120px]">{doc.source}</span>
                  <div className="flex items-center gap-3">
                    <span>{doc.chunk_count} {t('documents.chunks')}</span>
                    <span className="w-2 h-2 rounded-full bg-green-500" />
                    <button
                      onClick={() => setDeleteTarget({ source: doc.source, title: doc.title, chunkCount: doc.chunk_count })}
                      className="inline-flex items-center gap-1 text-[var(--error)] hover:bg-red-500/10 px-1.5 py-0.5 rounded transition-colors"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div data-testid="pagination" className="flex flex-col sm:flex-row items-center justify-between gap-4 mt-4 px-2">
              <div className="flex items-center gap-4">
                <span data-testid="page-info" className="text-sm text-[var(--text-tertiary)]">
                  {t("documents.pagination.total", { total: filtered.length, page, totalPages, interpolation: { escapeValue: false } })}
                </span>
                <div className="flex items-center gap-2">
                  <label className="text-xs text-[var(--text-tertiary)]">{t("documents.pagination.per_page", "每页")}</label>
                  <select
                    data-testid="page-size-select"
                    value={pageSize}
                    onChange={(e) => {
                      setPageSize(Number(e.target.value));
                      setPage(1);
                    }}
                    className="px-2 py-1 rounded border border-[var(--border)] bg-[var(--bg-secondary)] text-sm"
                  >
                    {PAGE_SIZE_OPTIONS.map((size) => (
                      <option key={size} value={size}>{size}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button
                  data-testid="page-prev"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="p-2 rounded-lg text-[var(--text-secondary)] hover:bg-[var(--surface-inset)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  aria-label={t("documents.pagination.prev", "上一页")}
                >
                  <ChevronLeft size={16} />
                </button>
                {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                  let pageNum: number;
                  if (totalPages <= 7) {
                    pageNum = i + 1;
                  } else if (page <= 4) {
                    pageNum = i + 1;
                  } else if (page >= totalPages - 3) {
                    pageNum = totalPages - 6 + i;
                  } else {
                    pageNum = page - 3 + i;
                  }
                  return (
                    <button
                      key={pageNum}
                      data-testid={`page-${pageNum}`}
                      onClick={() => setPage(pageNum)}
                      className={`w-8 h-8 rounded-lg text-sm font-medium transition-colors ${
                        pageNum === page
                          ? "bg-[var(--accent)] text-white"
                          : "text-[var(--text-secondary)] hover:bg-[var(--surface-inset)]"
                      }`}
                    >
                      {pageNum}
                    </button>
                  );
                })}
                <button
                  data-testid="page-next"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  className="p-2 rounded-lg text-[var(--text-secondary)] hover:bg-[var(--surface-inset)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  aria-label={t("documents.pagination.next", "下一页")}
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* 删除确认弹窗 */}
      {deleteTarget && (
        <ConfirmDialog
          open={!!deleteTarget}
          title={t("documents.delete.confirm_title", "删除文档")}
          message={
            <>
              {t("documents.delete.confirm_msg", `确定删除「{{title}}」及其 {{count}} 个 chunks？此操作不可撤销。`, {
                title: deleteTarget.title,
                count: deleteTarget.chunkCount,
              })}
            </>
          }
          confirmLabel={t("documents.delete.confirm", "确认删除")}
          cancelLabel={t("documents.delete.cancel", "取消")}
          variant="danger"
          onConfirm={() => {
            deleteDocument.mutate(deleteTarget.source, {
              onSettled: () => setDeleteTarget(null),
            });
          }}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  );
}
