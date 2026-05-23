/** Playground 页：单列 + 并排（最多 4 列） */

import { Plus } from 'lucide-react';
import { useState } from 'react';

import { SectionCard } from '@/core/components/table';
import { Button } from '@/core/components/ui/button';
import { toast } from '@/core/lib/toast';
import { ChatColumn } from '@/system/playground/components/chat-column';
import type { PlaygroundParams } from '@/system/playground/types/playground';

const MAX_COLUMNS = 4;

const newParams = (): PlaygroundParams => ({
  system_prompt: '',
  temperature: 0.7,
  top_p: 1,
  max_tokens: null,
  kb_ids: [],
});

export const PlaygroundPage = () => {
  const [columns, setColumns] = useState<PlaygroundParams[]>([newParams()]);

  const update = (i: number, next: PlaygroundParams) => {
    setColumns(prev => prev.map((c, idx) => (idx === i ? next : c)));
  };

  const add = () => {
    if (columns.length >= MAX_COLUMNS) {
      toast.warning(`最多 ${MAX_COLUMNS} 列`);
      return;
    }
    setColumns(prev => [...prev, newParams()]);
  };

  const remove = (i: number) => {
    setColumns(prev => prev.filter((_, idx) => idx !== i));
  };

  return (
    <SectionCard className="!p-0">
      <div className="flex items-center justify-between border-b border-stone-200/70 px-4 py-2.5">
        <div className="flex items-baseline gap-3">
          <h2 className="text-[14px] font-medium text-stone-900">Playground</h2>
          <span className="text-[11.5px] text-stone-500">
            直接调模型流式调试；不写 call_log；最多 {MAX_COLUMNS} 列并排
          </span>
        </div>
        <Button
          size="sm"
          variant="ghost"
          onClick={add}
          disabled={columns.length >= MAX_COLUMNS}
        >
          <Plus className="mr-1 h-3.5 w-3.5" />
          加列
        </Button>
      </div>
      <div
        className="grid h-[calc(100vh-180px)] gap-3 p-3 max-md:!grid-cols-1"
        style={{
          gridTemplateColumns: `repeat(${columns.length}, minmax(0, 1fr))`,
        }}
        title="P22.5：移动端 (<md) 强制单列 stack"
      >
        {columns.map((p, i) => (
          <ChatColumn
            key={i}
            index={columns.length > 1 ? i : undefined}
            params={p}
            onParamsChange={next => update(i, next)}
            onRemove={columns.length > 1 ? () => remove(i) : undefined}
          />
        ))}
      </div>
    </SectionCard>
  );
};
