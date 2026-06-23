import type { ReactNode, HTMLAttributes } from 'react';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}

export function Card({ children, className = '', hover = false, ...props }: CardProps) {
  return (
    <div
      {...props}
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
