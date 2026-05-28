/** 复制按钮 —— 浅 / 深两种皮肤 */
import { useState } from 'react';

import { Check, Copy } from 'lucide-react';

import { cn } from '@/core/lib/cn';

export const CopyButton = ({
  text,
  dark,
  className,
  title = '复制',
}: {
  text: string;
  dark?: boolean;
  className?: string;
  title?: string;
}) => {
  const [copied, setCopied] = useState(false);
  const onCopy = () =>
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });

  return (
    <button
      type="button"
      onClick={onCopy}
      title={title}
      className={cn(
        'rounded p-1 transition',
        dark
          ? 'text-stone-400 hover:bg-stone-700 hover:text-stone-100'
          : 'text-stone-400 hover:bg-stone-100 hover:text-stone-700',
        className,
      )}
    >
      {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
};
