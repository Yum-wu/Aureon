import type { ReactNode } from 'react';

interface CardProps {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}

export function Card({ children, className = '', hover = false }: CardProps) {
  return (
    <div
      className={`
        relative w-full rounded-lg border p-6 text-left shadow-xs
        bg-[var(--bg-secondary)] border-[var(--border)]
        ${hover ? 'hover:border-[var(--border-hover)] hover:shadow-sm transition-all duration-200 cursor-pointer' : ''}
        ${className}
      `}
    >
      {children}
    </div>
  );
}
