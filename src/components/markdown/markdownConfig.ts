/**
 * Stable ReactMarkdown components configuration.
 * Separate from component files to satisfy react-refresh ESLint rule.
 */
import { MarkdownCode } from './MarkdownCode';
import { MarkdownPre } from './MarkdownPre';

/** Stable components object for ReactMarkdown — file-level constant, no useMemo needed */
export const markdownComponents = {
  code: MarkdownCode,
  pre: MarkdownPre,
};
