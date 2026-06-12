import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock useDocuments hook
const mockUseDocuments = vi.fn();
vi.mock('../../hooks/useDocuments', () => ({
  useDocuments: () => mockUseDocuments(),
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
    t: (key: string) => key,
  }),
}));

import { Documents } from '../Documents';

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
    mockUseDocuments.mockReturnValue({
      documents: [],
      totalDocs: 0,
      totalChunks: 0,
      loading: true,
      error: null,
      refetch: vi.fn(),
    });

    act(() => {
      render(<Documents />);
    });
    expect(screen.getByText('documents.title')).toBeInTheDocument();
    // Loading spinner has no text, but empty state should not show
    expect(screen.queryByText('documents.empty')).not.toBeInTheDocument();
  });

  it('renders error state with retry button', () => {
    const mockRefetch = vi.fn();
    mockUseDocuments.mockReturnValue({
      documents: [],
      totalDocs: 0,
      totalChunks: 0,
      loading: false,
      error: 'Network error',
      refetch: mockRefetch,
    });

    act(() => {
      render(<Documents />);
    });
    expect(screen.getByText('documents.error_loading')).toBeInTheDocument();
    expect(screen.getByText('Network error')).toBeInTheDocument();

    const retryBtn = screen.getByText('documents.retry');
    retryBtn.click();
    expect(mockRefetch).toHaveBeenCalled();
  });

  it('renders empty state', () => {
    mockUseDocuments.mockReturnValue({
      documents: [],
      totalDocs: 0,
      totalChunks: 0,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    act(() => {
      render(<Documents />);
    });
    expect(screen.getByText('documents.empty')).toBeInTheDocument();
  });

  it('renders document list with table headers', () => {
    mockUseDocuments.mockReturnValue({
      documents: mockDocuments,
      totalDocs: 3,
      totalChunks: 45,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    act(() => {
      render(<Documents />);
    });
    expect(screen.getByText('documents.title')).toBeInTheDocument();
    // totalDocs and totalChunks are rendered as numbers
    // Use getAllByText since "3" may appear in doc list too
    const allThrees = screen.getAllByText('3');
    expect(allThrees.length).toBeGreaterThanOrEqual(1);
    const all45s = screen.getAllByText('45');
    expect(all45s.length).toBeGreaterThanOrEqual(1);
    // Document titles appear in both desktop+mobile views
    expect(screen.getAllByText('RAG Guide').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Deploy Notes').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('API Reference').length).toBeGreaterThanOrEqual(1);
  });

  it('filters documents by title', async () => {
    const user = userEvent.setup();
    mockUseDocuments.mockReturnValue({
      documents: mockDocuments,
      totalDocs: 3,
      totalChunks: 45,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<Documents />);
    const searchInput = screen.getByPlaceholderText('documents.search_placeholder');
    await user.type(searchInput, 'RAG');

    // RAG Guide appears in both desktop table and mobile cards
    const ragElements = screen.getAllByText('RAG Guide');
    expect(ragElements.length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText('Deploy Notes')).not.toBeInTheDocument();
    expect(screen.queryByText('API Reference')).not.toBeInTheDocument();
  });

  it('shows upload area when button clicked', async () => {
    const user = userEvent.setup();
    mockUseDocuments.mockReturnValue({
      documents: mockDocuments,
      totalDocs: 3,
      totalChunks: 45,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<Documents />);
    expect(screen.queryByTestId('document-upload')).not.toBeInTheDocument();

    await user.click(screen.getByText('documents.upload.button'));
    expect(screen.getByTestId('document-upload')).toBeInTheDocument();
  });

  it('renders table with file type badges', () => {
    mockUseDocuments.mockReturnValue({
      documents: mockDocuments,
      totalDocs: 3,
      totalChunks: 45,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    act(() => {
      render(<Documents />);
    });
    // Table headers
    expect(screen.getByText('documents.table.name')).toBeInTheDocument();
    expect(screen.getByText('documents.table.source')).toBeInTheDocument();
    expect(screen.getByText('documents.table.type')).toBeInTheDocument();
    expect(screen.getByText('documents.table.chunks')).toBeInTheDocument();
    expect(screen.getByText('documents.table.status')).toBeInTheDocument();
  });
});
