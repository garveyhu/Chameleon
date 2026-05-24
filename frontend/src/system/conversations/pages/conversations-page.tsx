/** 对话列表页 —— P21.4 PR #67；P23 D7 表格虚拟滚动（padding-row 技术，撑大列表） */

import { useQuery } from '@tanstack/react-query';
import { useVirtualizer } from '@tanstack/react-virtual';
import { MessageSquare } from 'lucide-react';
import { useRef } from 'react';
import { useNavigate } from 'react-router-dom';

import { SectionCard } from '@/core/components/table';
import { formatDateTime } from '@/core/lib/format';
import { conversationApi } from '@/system/conversations/services/conversation';

const ROW_H = 37;

export const ConversationsPage = () => {
  const nav = useNavigate();
  const listQ = useQuery({
    queryKey: ['conversations'],
    queryFn: () => conversationApi.list({ page: 1, page_size: 50 }),
  });
  const items = listQ.data?.items ?? [];

  const scrollRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_H,
    overscan: 12,
  });
  const virtualRows = virtualizer.getVirtualItems();
  const total = virtualizer.getTotalSize();
  // padding-row：上下两个占位 <tr> 撑出滚动高度，保持合法 table 标记
  const padTop = virtualRows.length ? virtualRows[0].start : 0;
  const padBottom = virtualRows.length
    ? total - virtualRows[virtualRows.length - 1].end
    : 0;

  return (
    <div className="space-y-3">
      <header className="flex items-center gap-2">
        <MessageSquare className="h-4 w-4 text-stone-500" />
        <h1 className="text-[15px] font-medium text-stone-800">对话</h1>
        <span className="text-[11px] text-stone-400">
          {listQ.data?.total ?? '...'} 个 session
        </span>
      </header>

      <SectionCard className="!p-0">
        <div
          ref={scrollRef}
          className="max-h-[calc(100vh-170px)] overflow-y-auto"
        >
          <table className="w-full table-fixed text-[12.5px]">
            <thead className="sticky top-0 z-10 bg-[var(--color-warm-2)]/40 text-[11px] text-stone-500 backdrop-blur">
              <tr>
                <th className="px-3 py-2 text-left">标题</th>
                <th className="w-40 px-3 py-2 text-left">Agent</th>
                <th className="w-32 px-3 py-2 text-left">App</th>
                <th className="w-40 px-3 py-2 text-right">最后消息</th>
                <th className="w-40 px-3 py-2 text-right">创建</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {padTop > 0 && (
                <tr>
                  <td colSpan={5} style={{ height: padTop }} />
                </tr>
              )}
              {virtualRows.map(vr => {
                const c = items[vr.index];
                return (
                  <tr
                    key={String(c.id)}
                    className="cursor-pointer hover:bg-warm-2/30"
                    style={{ height: ROW_H }}
                    onClick={() => nav(`/conversations/${c.session_id}`)}
                  >
                    <td className="truncate px-3 py-2 font-medium text-stone-800">
                      {c.title || (
                        <span className="text-stone-400">(无标题)</span>
                      )}
                    </td>
                    <td className="truncate px-3 py-2 font-mono text-[11px] text-stone-600">
                      {c.agent_key}
                    </td>
                    <td className="truncate px-3 py-2 font-mono text-[11px] text-stone-500">
                      {c.app_id}
                    </td>
                    <td className="px-3 py-2 text-right text-[11.5px] text-stone-500">
                      {c.last_message_at
                        ? formatDateTime(c.last_message_at)
                        : '—'}
                    </td>
                    <td className="px-3 py-2 text-right text-[11.5px] text-stone-500">
                      {formatDateTime(c.created_at)}
                    </td>
                  </tr>
                );
              })}
              {padBottom > 0 && (
                <tr>
                  <td colSpan={5} style={{ height: padBottom }} />
                </tr>
              )}
              {items.length === 0 && (
                <tr>
                  <td
                    colSpan={5}
                    className="px-3 py-12 text-center text-[12px] text-stone-400"
                  >
                    暂无 session（先通过 Playground / agent invoke 创建）
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
};
