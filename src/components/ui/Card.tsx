import type { ReactNode } from 'react';

interface CardProps {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}

export function Card({ children, className = '', hover = false }: CardProps) {
  return (
    <div
      className={`glass-card rounded-xl p-6 ${hover ? 'hover:scale-[1.02] transition-all duration-300' : ''} ${className}`}
    >
      {children}
    </div>
  );
}