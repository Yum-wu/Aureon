/**
 * 通用管理表格组件
 * 支持排序、分页、行操作、加载骨架屏、空状态
 */

import { useState, useCallback, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

/** 列定义 */
export interface AdminColumn<T = Record<string, unknown>> {
  /** 数据字段名 */
  key: string;
  /** 列标题 */
  label: string;
  /** 是否可排序 */
  sortable?: boolean;
  /** 自定义渲染 */
  render?: (row: T, index: number) => ReactNode;
}

/** 行操作按钮 */
export interface AdminAction<T = Record<string, unknown>> {
  /** 操作标签 */
  label: string;
  /** 图标字符 */
  icon?: string;
  /** 点击回调 */
  onClick: (row: T) => void;
  /** 按钮变体 */
  variant?: 'default' | 'danger';
}

/** 分页配置 */
export interface PaginationState {
  page: number;
  pageSize: number;
  total: number;
}

interface AdminTableProps<T = Record<string, unknown>> {
  /** 列定义 */
  columns: AdminColumn<T>[];
  /** 数据行 */
  data: T[];
  /** 加载状态 */
  loading?: boolean;
  /** 分页状态 */
  pagination?: PaginationState;
  /** 排序回调 */
  onSort?: (key: string, direction: 'asc' | 'desc') => void;
  /** 分页变更回调 */
  onPageChange?: (page: number) => void;
  /** 行点击回调 */
  onRowClick?: (row: T) => void;
  /** 行操作按钮 */
  actions?: AdminAction<T>[];
  /** 额外类名 */
  className?: string;
}

export function AdminTable<T extends Record<string, unknown>>({
  columns,
  data,
  loading = false,
  pagination,
  onSort,
  onPageChange,
  onRowClick,
  actions,
  className = '',
}: AdminTableProps<T>) {
  const { t } = useTranslation();
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  const handleSort = useCallback(
    (key: string) => {
      const newDir = sortKey === key && sortDir === 'asc' ? 'desc' : 'asc';
      setSortKey(key);
      setSortDir(newDir);
      onSort?.(key, newDir);
    },
    [sortKey, sortDir, onSort],
  );

  const totalPages = pagination ? Math.ceil(pagination.total / pagination.pageSize) : 1;

  return (
    <div className={`overflow-x-auto rounded-lg border border-[var(--border)] ${className}`}>
      <table className="w-full text-sm">
        {/* 表头 */}
        <thead>
          <tr className="border-b border-[var(--border)] bg-[var(--bg-tertiary)]">
            {columns.map((col) => (
              <th
                key={col.key}
                className={`px-4 py-3 text-left text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wider ${
                  col.sortable ? 'cursor-pointer hover:text-[var(--text-secondary)] select-none' : ''
                }`}
                onClick={col.sortable ? () => handleSort(col.key) : undefined}
              >
                <span className="inline-flex items-center gap-1">
                  {col.label}
                  {col.sortable && sortKey === col.key && (
                    <span className="text-[var(--accent)]">{sortDir === 'asc' ? '↑' : '↓'}</span>
                  )}
                </span>
              </th>
            ))}
            {actions && actions.length > 0 && (
              <th className="px-4 py-3 text-right text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wider">
                {t('admin.workspaces.columns.actions')}
              </th>
            )}
          </tr>
        </thead>

        {/* 表体 */}
        <tbody>
          {loading ? (
            /* 加载骨架屏 */
            Array.from({ length: 3 }).map((_, i) => (
              <tr key={`skeleton-${i}`} className="border-b border-[var(--border-subtle)]">
                {columns.map((col) => (
                  <td key={col.key} className="px-4 py-3">
                    <div className="h-4 bg-white/[0.04] rounded animate-pulse" />
                  </td>
                ))}
                {actions && actions.length > 0 && <td className="px-4 py-3" />}
              </tr>
            ))
          ) : data.length === 0 ? (
            /* 空状态 */
            <tr>
              <td
                colSpan={columns.length + (actions ? 1 : 0)}
                className="px-4 py-12 text-center text-[var(--text-tertiary)]"
              >
                {t('admin.no_traces')}
              </td>
            </tr>
          ) : (
            data.map((row, rowIndex) => (
              <tr
                key={rowIndex}
                className={`border-b border-[var(--border-subtle)] transition-colors ${
                  onRowClick ? 'cursor-pointer hover:bg-white/[0.02]' : ''
                }`}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
              >
                {columns.map((col) => (
                  <td key={col.key} className="px-4 py-3 text-[var(--text-primary)]">
                    {col.render ? col.render(row, rowIndex) : String(row[col.key] ?? '')}
                  </td>
                ))}
                {actions && actions.length > 0 && (
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {actions.map((action, actionIndex) => (
                        <button
                          key={actionIndex}
                          onClick={(e) => {
                            e.stopPropagation();
                            action.onClick(row);
                          }}
                          className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors ${
                            action.variant === 'danger'
                              ? 'text-red-400 hover:bg-red-500/10'
                              : 'text-[var(--text-secondary)] hover:bg-white/[0.05] hover:text-[var(--text-primary)]'
                          }`}
                        >
                          {action.icon && <span>{action.icon}</span>}
                          {action.label}
                        </button>
                      ))}
                    </div>
                  </td>
                )}
              </tr>
            ))
          )}
        </tbody>
      </table>

      {/* 分页 */}
      {pagination && totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-[var(--border)]">
          <span className="text-xs text-[var(--text-tertiary)]">
            {pagination.total} 条记录
          </span>
          <div className="flex items-center gap-1">
            <button
              disabled={pagination.page <= 1}
              onClick={() => onPageChange?.(pagination.page - 1)}
              className="px-2 py-1 rounded text-xs text-[var(--text-secondary)] hover:bg-white/[0.05] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              ←
            </button>
            {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
              const page = i + 1;
              return (
                <button
                  key={page}
                  onClick={() => onPageChange?.(page)}
                  className={`px-2.5 py-1 rounded text-xs transition-colors ${
                    page === pagination.page
                      ? 'bg-[var(--accent)] text-white font-medium'
                      : 'text-[var(--text-secondary)] hover:bg-white/[0.05]'
                  }`}
                >
                  {page}
                </button>
              );
            })}
            <button
              disabled={pagination.page >= totalPages}
              onClick={() => onPageChange?.(pagination.page + 1)}
              className="px-2 py-1 rounded text-xs text-[var(--text-secondary)] hover:bg-white/[0.05] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
