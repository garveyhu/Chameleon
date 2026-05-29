/** Playground 输入框 —— 文本 + 附件 + 发送/停止
 *
 * 不绑定具体列：父级给 onSend(text, attachments)，对比模式下可一次广播到所有列。
 */

import { Send, Square } from 'lucide-react';
import { useCallback, useState } from 'react';

import { Button } from '@/core/components/ui/button';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import { FileAttachButton } from '@/system/playground/components/file-attach-button';
import type { UploadResult } from '@/system/files/services/file-upload';

interface Props {
  onSend: (text: string, attachments: UploadResult[]) => void | Promise<void>;
  streaming: boolean;
  onStop?: () => void;
  placeholder?: string;
  className?: string;
}

export const Composer = ({ onSend, streaming, onStop, placeholder, className }: Props) => {
  const [input, setInput] = useState('');
  const [attachments, setAttachments] = useState<UploadResult[]>([]);

  const doSend = useCallback(async () => {
    const text = input.trim();
    if (!text && attachments.length === 0) return;
    setInput('');
    setAttachments([]);
    await onSend(text, attachments);
  }, [input, attachments, onSend]);

  return (
    <div className={cn('rounded-xl border border-stone-200 bg-white p-2.5 shadow-[0_1px_2px_rgba(0,0,0,.03)]', className)}>
      <Textarea
        value={input}
        onChange={e => setInput(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            void doSend();
          }
        }}
        rows={2}
        placeholder={placeholder ?? '输入消息… ⌘/Ctrl+Enter 发送'}
        className="!border-0 !p-0 text-[12.5px] !shadow-none focus-visible:!ring-0"
      />
      <div className="mt-1.5 flex items-center gap-2">
        <FileAttachButton
          attachments={attachments}
          onAttached={a => setAttachments(prev => [...prev, a])}
          onRemove={id => setAttachments(prev => prev.filter(a => a.object_id !== id))}
          disabled={streaming}
        />
        <div className="ml-auto">
          {streaming ? (
            <Button size="sm" variant="ghost" onClick={onStop}>
              <Square className="mr-1 h-3 w-3" />
              停止
            </Button>
          ) : (
            <Button size="sm" onClick={doSend} disabled={!input.trim() && attachments.length === 0}>
              <Send className="mr-1 h-3 w-3" />
              发送
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};
