import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

// Mock useDocumentsQuery (TanStack Query)
const mockUseDocumentsQuery = vi.fn();
vi.mock('../../hooks/useDocumentsQuery', () => ({
  useDocumentsQuery: () => mockUseDocumentsQuery(),
  useDocuments: () => mockUseDocumentsQuery().data?.documents ?? [],
  prefetchDocuments: vi.fn(),
}));

// Mock useBlogConfig hook (async fetch causes act() warnings)
vi.mock('../../hooks/useBlogConfig', () => ({
  useBlogConfig: () => ({ config: null, loading: true }),
}));

// Mock DocumentUpload component
vi.mock('../../components/documents/DocumentUpload', () => ({
  DocumentUpload: ({ onUploadSuccess }: { onUploadSuccess: () => void }) => (
    <div data-testid="document-upload">
      <button onClick={onUploadSuccess}>Mock Upload</button>
    </div>
  ),
}));

// Mock react-i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (opts) return key.replace(/\{\{(\w+)\}\}/g, (_, k) => String(opts[k] ?? ''));
      return key;
    },
  }),
}));

// Mock Breadcrumb (requires Router context)
vi.mock('../../components/ui/Breadcrumb', () => ({
  Breadcrumb: () => null,
}));

import { Documents } from '../Documents';

// Helper to wrap in QueryClientProvider
function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

const mockDocuments = [
  { title: 'RAG Guide', source: 'rag-guide.md', file_type: 'md', chunk_count: 15, status: 'ready' },
  { title: 'Deploy Notes', source: 'deploy.txt', file_type: 'txt', chunk_count: 8, status: 'ready' },
  { title: 'API Reference', source: 'api-ref.pdf', file_type: 'pdf', chunk_count: 22, status: 'ready' },
];

describe('Documents', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state', () => {
    mockUseDocumentsQuery.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      refetch: vi.fn(),
    });

    act(() => {
      renderWithQueryClient(<Documents />);
    });
    expect(screen.getByText('documents.title')).toBeInTheDocument();
    expect(screen.queryByText('documents.empty')).not.toBeInTheDocument();
  });

  it('renders error state with retry button', () => {
    const mockRefetch = vi.fn();
    mockUseDocumentsQuery.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('Network error'),
      refetch: mockRefetch,
    });

    act(() => {
      renderWithQueryClient(<Documents />);
    });
    expect(screen.getByText('documents.error_loading')).toBeInTheDocument();
    expect(screen.getByText('Network error')).toBeInTheDocument();

    const retryBtn = screen.getByText('documents.retry');
    retryBtn.click();
    expect(mockRefetch).toHaveBeenCalled();
  });

  it('renders empty state', () => {
    mockUseDocumentsQuery.mockReturnValue({
      data: { documents: [], totalDocs: 0, totalChunks: 0 },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    act(() => {
      renderWithQueryClient(<Documents />);
    });
    expect(screen.getByText('documents.empty')).toBeInTheDocument();
  });

  it('renders document list with table headers', () => {
    mockUseDocumentsQuery.mockReturnValue({
      data: { documents: mockDocuments, totalDocs: 3, totalChunks: 45 },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    act(() => {
      renderWithQueryClient(<Documents />);
    });
    expect(screen.getByText('documents.title')).toBeInTheDocument();
    const allThrees = screen.getAllByText('3');
    expect(allThrees.length).toBeGreaterThanOrEqual(1);
    const all45s = screen.getAllByText('45');
    expect(all45s.length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('RAG Guide').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Deploy Notes').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('API Reference').length).toBeGreaterThanOrEqual(1);
  });

  it('filters documents by title', async () => {
    const user = userEvent.setup();
    mockUseDocumentsQuery.mockReturnValue({
      data: { documents: mockDocuments, totalDocs: 3, totalChunks: 45 },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithQueryClient(<Documents />);
    const searchInput = screen.getByPlaceholderText('documents.search_placeholder');
    await user.type(searchInput, 'RAG');

    const ragElements = screen.getAllByText('RAG Guide');
    expect(ragElements.length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText('Deploy Notes')).not.toBeInTheDocument();
    expect(screen.queryByText('API Reference')).not.toBeInTheDocument();
  });

  it('shows upload area when button clicked', async () => {
    const user = userEvent.setup();
    mockUseDocumentsQuery.mockReturnValue({
      data: { documents: mockDocuments, totalDocs: 3, totalChunks: 45 },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithQueryClient(<Documents />);
    expect(screen.queryByTestId('document-upload')).not.toBeInTheDocument();

    await user.click(screen.getByText('documents.upload.button'));
    expect(screen.getByTestId('document-upload')).toBeInTheDocument();
  });

  it('renders table with file type badges', () => {
    mockUseDocumentsQuery.mockReturnValue({
      data: { documents: mockDocuments, totalDocs: 3, totalChunks: 45 },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    act(() => {
      renderWithQueryClient(<Documents />);
    });
    expect(screen.getByText('documents.table.name')).toBeInTheDocument();
    expect(screen.getByText('documents.table.source')).toBeInTheDocument();
    expect(screen.getByText('documents.table.type')).toBeInTheDocument();
    expect(screen.getByText('documents.table.chunks')).toBeInTheDocument();
    expect(screen.getByText('documents.table.status')).toBeInTheDocument();
  });
});
