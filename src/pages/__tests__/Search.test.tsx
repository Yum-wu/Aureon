import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Mock rag service
const mockStreamRAGQuery = vi.fn();
vi.mock('../../services/rag', () => ({
  streamRAGQuery: (...args: unknown[]) => mockStreamRAGQuery(...args),
}));

// Mock authFetch (used by Search useEffect for suggestions)
vi.mock('../../services/authFetch', () => ({
  authFetch: () => Promise.resolve({
    ok: true,
    json: () => Promise.resolve({ suggestions: [] }),
  }),
}));

// Mock react-i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (opts && typeof opts === 'object') {
        return Object.entries(opts).reduce(
          (str, [k, v]) => str.replace(`{{${k}}}`, String(v)),
          key
        );
      }
      return key;
    },
  }),
}));

// Mock child components
vi.mock('../../components/search/SearchBar', () => ({
  SearchBar: ({ value, onChange, onSearch, isLoading }: Record<string, unknown>) => (
    <div data-testid="search-bar">
      <input
        data-testid="search-input"
        value={value as string}
        onChange={(e) => (onChange as (v: string) => void)(e.target.value)}
      />
      <button data-testid="search-btn" onClick={onSearch as () => void} disabled={isLoading as boolean}>
        Search
      </button>
    </div>
  ),
}));

vi.mock('../../components/search/StreamingAnswer', () => ({
  StreamingAnswer: ({ content, isStreaming }: Record<string, unknown>) => (
    <div data-testid="streaming-answer">
      {content as string}
      {isStreaming ? ' (streaming)' : ''}
    </div>
  ),
}));

vi.mock('../../components/search/CitationList', () => ({
  CitationList: ({ citations }: Record<string, unknown>) => (
    <div data-testid="citation-list">{(citations as unknown[]).length} citations</div>
  ),
}));

import { Search } from '../Search';

describe('Search', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStreamRAGQuery.mockResolvedValue(undefined);
  });

  it('renders initial state with title and empty search', async () => {
    await act(async () => {
      render(<MemoryRouter><Search /></MemoryRouter>);
    });
    expect(screen.getByText('search.title')).toBeInTheDocument();
    expect(screen.getByText('search.subtitle')).toBeInTheDocument();
    expect(screen.getByTestId('search-bar')).toBeInTheDocument();
  });

  it('does not show answer area initially', async () => {
    await act(async () => {
      render(<MemoryRouter><Search /></MemoryRouter>);
    });
    expect(screen.queryByTestId('streaming-answer')).not.toBeInTheDocument();
  });

  it('shows error when query exceeds max length', async () => {
    const user = userEvent.setup();
    await act(async () => {
      render(<MemoryRouter><Search /></MemoryRouter>);
    });

    const input = screen.getByTestId('search-input');
    // Type a short query then simulate the length check
    await user.type(input, 'short');
    // Directly set the input value to simulate a long query
    // and trigger search via button click
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value'
    )!.set!;
    nativeInputValueSetter.call(input, 'a'.repeat(1001));
    await act(async () => {
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await user.click(screen.getByTestId('search-btn'));

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(mockStreamRAGQuery).not.toHaveBeenCalled();
  });

  it('shows error from stream callback', async () => {
    mockStreamRAGQuery.mockImplementation(async (_q: string, opts: { onError: (msg: string) => void }) => {
      opts.onError('Server error occurred');
    });

    const user = userEvent.setup();
    await act(async () => {
      render(<MemoryRouter><Search /></MemoryRouter>);
    });

    const input = screen.getByTestId('search-input');
    await user.type(input, 'test query');
    await user.click(screen.getByTestId('search-btn'));

    expect(screen.getByText('Server error occurred')).toBeInTheDocument();
  });

  it('clears error when typing new query', async () => {
    mockStreamRAGQuery.mockImplementation(async (_q: string, opts: { onError: (msg: string) => void }) => {
      opts.onError('Error!');
    });

    const user = userEvent.setup();
    await act(async () => {
      render(<MemoryRouter><Search /></MemoryRouter>);
    });

    const input = screen.getByTestId('search-input');
    await user.type(input, 'bad query');
    await user.click(screen.getByTestId('search-btn'));
    expect(screen.getByText('Error!')).toBeInTheDocument();

    await user.type(input, 'x');
    expect(screen.queryByText('Error!')).not.toBeInTheDocument();
  });

  it('shows answer area after search', async () => {
    mockStreamRAGQuery.mockImplementation(async (_q: string, opts: { onToken: (token: string) => void }) => {
      opts.onToken('Hello ');
      opts.onToken('world');
    });

    const user = userEvent.setup();
    await act(async () => {
      render(<MemoryRouter><Search /></MemoryRouter>);
    });

    const input = screen.getByTestId('search-input');
    await user.type(input, 'test query');
    await user.click(screen.getByTestId('search-btn'));

    expect(screen.getByTestId('streaming-answer')).toBeInTheDocument();
    expect(screen.getByText(/Hello world/)).toBeInTheDocument();
  });

  it('displays character count', async () => {
    await act(async () => {
      render(<MemoryRouter><Search /></MemoryRouter>);
    });
    expect(screen.getByText('0/1000')).toBeInTheDocument();
  });
});
