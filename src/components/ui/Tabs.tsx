/**
 * Tabs — 标签页切换组件
 * Canvas 设计系统 .tabs/.tab 模式的 React 实现
 */

import { type ReactNode } from 'react';

interface Tab {
  id: string;
  label: string;
  icon?: ReactNode;
}

interface TabsProps {
  tabs: Tab[];
  activeTab: string;
  onChange: (tabId: string) => void;
  /** 附加 CSS 类名 */
  className?: string;
}

export function Tabs({ tabs, activeTab, onChange, className }: TabsProps) {
  return (
    <div
      className={className}
      role="tablist"
      style={{
        display: 'flex',
        borderBottom: '1px solid var(--border)',
        gap: 0,
        overflowX: 'auto',
        WebkitOverflowScrolling: 'touch',
        scrollbarWidth: 'none',
      }}
    >
      {tabs.map((tab) => {
        const active = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(tab.id)}
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 14,
              fontWeight: 500,
              color: active ? 'var(--seed-accent)' : 'var(--fg-tertiary)',
              padding: 'var(--space-3) var(--space-5)',
              border: 'none',
              background: 'none',
              cursor: 'pointer',
              position: 'relative',
              transition: 'color var(--duration-fast) var(--ease-out)',
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-2)',
              flexShrink: 0,
              whiteSpace: 'nowrap',
            }}
            onMouseEnter={(e) => {
              if (!active) e.currentTarget.style.color = 'var(--fg)';
            }}
            onMouseLeave={(e) => {
              if (!active) e.currentTarget.style.color = 'var(--fg-tertiary)';
            }}
          >
            {tab.icon}
            {tab.label}
            {active && (
              <span
                style={{
                  position: 'absolute',
                  bottom: -1,
                  left: 0,
                  right: 0,
                  height: 2,
                  background: 'var(--seed-accent)',
                  borderRadius: '1px 1px 0 0',
                }}
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
