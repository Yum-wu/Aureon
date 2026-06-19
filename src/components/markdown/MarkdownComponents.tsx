/**
 * Stable ReactMarkdown components for use across the app.
 * Extracted from MessageItem.tsx to avoid re-creation on every render.
 */
import { lazy, Suspense } from 'react';

const Highlighter = lazy(() => import('../SyntaxHighlighterWrapper'));

/** Code block with syntax highlighting and copy button */
function MarkdownCode({ className, children, ...props }: React.ClassAttributes<HTMLElement> &
  React.HTMLAttributes<HTMLElement> & { className?: string; children?: React.ReactNode }) {
  const match = /language-(\w+)/.exec(className || "");
  const codeString = String(children).replace(/\n$/, "");
  if (match) {
    return <MarkdownFencedCode language={match[1]} code={codeString} />;
  }
  return (
    <code className="px-1.5 py-0.5 rounded text-sm font-mono bg-[var(--accent-soft)] text-[var(--accent)]" {...props}>
      {children}
    </code>
  );
}

/** Fenced code block (```lang ... ```) with syntax highlighting + copy */
function MarkdownFencedCode({ language, code }: { language?: string; code: string }) {
  return (
    <div className="relative group rounded-lg overflow-hidden my-2">
      <div className="flex items-center justify-between bg-[#1a1b26] px-4 py-1.5 text-xs text-[var(--text-tertiary)]">
        <span>{language || "code"}</span>
        <button
          onClick={() => navigator.clipboard.writeText(code)}
          className="text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
        >
          📋  {/* 这个 emoji 会被另一个任务替换为 Lucide Copy 图标 */}
        </button>
      </div>
      <Suspense
        fallback={
          <pre className="bg-[#111118] text-[var(--text-secondary)] p-4 text-sm overflow-x-auto m-0">
            <code>{code}</code>
          </pre>
        }
      >
        <Highlighter language={language || "text"} code={code} showLineNumbers={code.split("\n").length > 3} />
      </Suspense>
    </div>
  );
}

/** pre tag wrapper */
function MarkdownPre({ children }: { children?: React.ReactNode }) {
  return <div className="my-2">{children}</div>;
}

/** Stable components object for ReactMarkdown - file-level constant, no useMemo needed */
export const markdownComponents = {
  code: MarkdownCode,
  pre: MarkdownPre,
};
