import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';

// Mock i18n
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

// Mock useBenchmark
vi.mock('../../hooks/useBenchmark', () => ({
  useBenchmark: () => ({
    data: {
      metrics: [
        { label: 'Recall@3 (Hybrid)', value: '96.08%' },
        { label: 'Streaming TTFT', value: '~310ms' },
      ],
    },
    loading: false,
  }),
}));

// Mock authFetch for Admin page
vi.mock('../../services/authFetch', () => ({
  authFetch: vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) }),
}));

// Mock Admin sub-components
vi.mock('../../components/admin/AdminLayout', () => ({
  AdminLayout: ({ children }: { children: React.ReactNode }) => <div data-testid="admin-layout">{children}</div>,
}));
vi.mock('../../components/admin/AdminTable', () => ({
  AdminTable: () => <div data-testid="admin-table" className="overflow-x-auto">table</div>,
}));
vi.mock('../../components/admin/AdminForm', () => ({
  AdminForm: () => <div data-testid="admin-form">form</div>,
}));
vi.mock('../../components/admin/StatusBadge', () => ({
  StatusBadge: () => <span data-testid="status-badge">badge</span>,
}));
vi.mock('../../components/admin/ConfirmDialog', () => ({
  ConfirmDialog: () => <div data-testid="confirm-dialog">dialog</div>,
}));
vi.mock('../../components/ui/Card', () => ({
  Card: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import Benchmark from '../Benchmark';
import Admin from '../Admin';

describe('Page Scroll Behavior', () => {
  describe('Benchmark Page', () => {
    it('should have scrollable container', () => {
      const { container } = render(
        <BrowserRouter>
          <Benchmark />
        </BrowserRouter>
      );

      // Find the main scrollable container
      const scrollable = container.querySelector('.overflow-y-auto');
      expect(scrollable).toBeInTheDocument();
    });

    it('should allow vertical scrolling when content overflows', () => {
      const { container } = render(
        <BrowserRouter>
          <Benchmark />
        </BrowserRouter>
      );

      const scrollable = container.querySelector('.overflow-y-auto');
      expect(scrollable).toHaveClass('overflow-y-auto');
    });
  });

  describe('Admin Page', () => {
    it('should render without crashing', () => {
      const { container } = render(
        <BrowserRouter>
          <Admin />
        </BrowserRouter>
      );

      // Admin 页面成功渲染
      expect(container.querySelector('[data-testid="admin-layout"]')).toBeInTheDocument();
    });

    it('should have admin layout structure', () => {
      const { container } = render(
        <BrowserRouter>
          <Admin />
        </BrowserRouter>
      );

      // Admin 使用 AdminLayout 组件
      expect(container.querySelector('[data-testid="admin-layout"]')).toBeTruthy();
    });
  });
});
