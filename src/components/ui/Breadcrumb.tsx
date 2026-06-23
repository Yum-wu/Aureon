/**
 * Breadcrumb — 面包屑导航组件
 * Canvas 设计系统 .breadcrumb 模式的 React 实现
 */

import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ChevronRight } from 'lucide-react';

interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface BreadcrumbProps {
  items?: BreadcrumbItem[];
  /** 如果未提供 items，自动从路径生成 */
  auto?: boolean;
}

/** 路径段到 i18n key 的映射 */
const PATH_LABELS: Record<string, string> = {
  dashboard: 'app.nav.dashboard',
  search: 'app.nav.search',
  documents: 'app.nav.documents',
  analytics: 'app.nav.analytics',
  architecture: 'app.nav.architecture',
  admin: 'app.nav.admin',
  cost: 'app.nav.cost',
  crew: 'app.nav.crew',
};

export function Breadcrumb({ items, auto }: BreadcrumbProps) {
  const { t } = useTranslation();
  const location = useLocation();

  const crumbs: BreadcrumbItem[] = items ?? (auto ? generateFromPath(location.pathname, t) : []);

  if (crumbs.length === 0) return null;

  return (
    <nav aria-label="Breadcrumb" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', fontSize: 13, color: 'var(--fg-muted)' }}>
      {crumbs.map((item, i) => {
        const isLast = i === crumbs.length - 1;
        return (
          <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            {i > 0 && (
              <ChevronRight size={14} style={{ color: 'var(--fg-subtle)', flexShrink: 0 }} />
            )}
            {item.href && !isLast ? (
              <Link
                to={item.href}
                style={{
                  color: 'var(--fg-tertiary)',
                  textDecoration: 'none',
                  transition: 'color var(--duration-fast) var(--ease-out)',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--fg)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--fg-tertiary)'; }}
              >
                {item.label}
              </Link>
            ) : (
              <span
                style={{
                  color: isLast ? 'var(--fg)' : 'var(--fg-tertiary)',
                  fontWeight: isLast ? 500 : 400,
                }}
              >
                {item.label}
              </span>
            )}
          </span>
        );
      })}
    </nav>
  );
}

function generateFromPath(pathname: string, t: (key: string) => string): BreadcrumbItem[] {
  const segments = pathname.split('/').filter(Boolean);
  if (segments.length === 0) return [{ label: 'Aureon' }];

  const crumbs: BreadcrumbItem[] = [{ label: 'Aureon', href: '/' }];

  let currentPath = '';
  for (const seg of segments) {
    currentPath += `/${seg}`;
    const labelKey = PATH_LABELS[seg];
    crumbs.push({
      label: labelKey ? t(labelKey) : seg.charAt(0).toUpperCase() + seg.slice(1),
      href: currentPath,
    });
  }

  return crumbs;
}
