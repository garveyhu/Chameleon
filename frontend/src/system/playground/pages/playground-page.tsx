/** Playground 页：单列 + 并排（最多 4 列）—— 状态全在 core/stores/chat */

import { Plus } from 'lucide-react';

import { SectionCard } from '@/core/components/table';
import { Button } from '@/core/components/ui/button';
import { MAX_COLUMNS, useChatStore } from '@/core/stores/chat';
import { ChatColumn } from '@/system/playground/components/chat-column';

export const PlaygroundPage = () => {
  const columns = useChatStore(s => s.columns);
  const addColumn = useChatStore(s => s.addColumn);
  const removeColumn = useChatStore(s => s.removeColumn);
  const multi = columns.length > 1;

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
          onClick={addColumn}
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
        {columns.map((col, i) => (
          <ChatColumn
            key={col.id}
            columnId={col.id}
            index={multi ? i : undefined}
            onRemove={multi ? () => removeColumn(col.id) : undefined}
          />
        ))}
      </div>
    </SectionCard>
  );
};
