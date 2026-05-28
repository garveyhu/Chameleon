/** 代码块 —— 深色 pre + 可复制按钮（无外部高亮库依赖） */
import { cn } from '@/core/lib/cn';

import { CopyButton } from './copy-button';

interface Props {
  text: string;
  language?: string;
  /** 顶部标签（如 "cURL"、"200 - application/json"） */
  label?: string;
  className?: string;
}

export const CodeBlock = ({ text, label, language, className }: Props) => (
  <div className={cn('group relative overflow-hidden rounded-xl bg-stone-900 shadow-sm', className)}>
    {label && (
      <div className="flex items-center justify-between border-b border-stone-700/60 px-3.5 py-1.5">
        <span className="font-mono text-[10.5px] tracking-wide text-stone-400 uppercase">
          {label}
        </span>
        {language && (
          <span className="rounded bg-stone-800 px-1.5 py-0.5 font-mono text-[10px] text-stone-400">
            {language}
          </span>
        )}
      </div>
    )}
    <pre className="overflow-x-auto px-4 py-3 font-mono text-[12px] leading-relaxed whitespace-pre text-stone-100">
      {text}
    </pre>
    <div className="absolute top-1.5 right-2">
      <CopyButton text={text} dark className="opacity-0 transition group-hover:opacity-100" />
    </div>
  </div>
);
