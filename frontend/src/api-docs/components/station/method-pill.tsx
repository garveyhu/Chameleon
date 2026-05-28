/** Method 标签小药丸 —— 复用 GET / POST 配色 */
import { cn } from '@/core/lib/cn';

const METHOD_TONE: Record<string, string> = {
  POST: 'bg-emerald-100 text-emerald-700',
  GET: 'bg-sky-100 text-sky-700',
};

export const MethodPill = ({
  method,
  size = 'md',
  className,
}: {
  method: 'GET' | 'POST';
  size?: 'sm' | 'md';
  className?: string;
}) => (
  <span
    className={cn(
      'inline-flex shrink-0 items-center rounded font-mono font-bold tracking-wide',
      METHOD_TONE[method],
      size === 'sm' ? 'px-1.5 py-0.5 text-[9.5px]' : 'px-2 py-0.5 text-[10.5px]',
      className,
    )}
  >
    {method}
  </span>
);
