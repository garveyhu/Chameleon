/** 应用详情「会话」tab —— 该应用的会话列表（ChatSession 维度，分页）。
 *
 * callLogApi.listSessions（按 agent_key 过滤）。点行进会话详情（/conversations/{id}，
 * 渲染多模态消息含图片/视频）。
 */
import { useState } from 'react';

import { useQuery } from '@tanstack/react-query';
import { ArrowRight, MessagesSquare } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';

import { EmptyState } from '@/core/components/common/empty-state';
import { DataTable, type DataTableColumn, TablePagination } from '@/core/components/table';
import { formatDateTime } from '@/core/lib/format';
import { ChannelLabel } from '@/system/call_logs/components/ledger-badges';
import { DetailSection } from '@/system/agents/components/detail-section';
import { callLogApi } from '@/system/call_logs/services/call-log';
import type { SessionItem } from '@/system/call_logs/types/call-log';

interface Props {
  agentKey: string;
}

export const AgentSessionsTab = ({ agentKey }: Props) => {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const listQ = useQuery({
    queryKey: ['agent-session-list', agentKey, page, pageSize],
    queryFn: () =>
      callLogApi.listSessions({ page, page_size: pageSize, agent_key: agentKey }),
    enabled: !!agentKey,
  });

  const rows = listQ.data?.items ?? [];
  const total = listQ.data?.total ?? 0;

  const columns: DataTableColumn<SessionItem>[] = [
    {
      key: 'title',
      header: '会话',
      render: s => (
        <div className="min-w-0">
          <div className="truncate text-[12.5px] font-medium text-stone-800">
            {s.title || '未命名会话'}
          </div>
          <div className="truncate font-mono text-[10.5px] text-stone-400">
            {s.session_id}
          </div>
        </div>
      ),
    },
    {
      key: 'channel',
      header: '渠道',
      width: 92,
      render: s =>
        s.channel ? <ChannelLabel channel={s.channel} /> : <span className="text-stone-400">—</span>,
    },
    {
      key: 'turns',
      header: '轮次',
      width: 70,
      align: 'right',
      render: s => (
        <span className="tnum font-mono text-[11.5px] text-stone-700">{s.turn_count}</span>
      ),
    },
    {
      key: 'end_user',
      header: '终端用户',
      width: 140,
      render: s =>
        s.end_user_id ? (
          <span className="truncate font-mono text-[11px] text-stone-500">{s.end_user_id}</span>
        ) : (
          <span className="text-stone-400">—</span>
        ),
    },
    {
      key: 'last',
      header: '最后消息',
      width: 150,
      render: s => (
        <span className="tnum font-mono text-[11.5px] text-stone-500">
          {formatDateTime(s.last_message_at ?? s.created_at)}
        </span>
      ),
    },
  ];

  return (
    <DetailSection
      icon={MessagesSquare}
      title="会话"
      desc={total > 0 ? `共 ${total} 个会话` : '该应用的对话记录'}
      action={
        <Link
          to={`/sessions?agent_key=${encodeURIComponent(agentKey)}`}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12px] font-medium text-blue-600 transition hover:bg-blue-50"
        >
          会话账本
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      }
      flush
    >
      <DataTable
        columns={columns}
        rows={rows}
        rowKey="session_id"
        loading={listQ.isLoading}
        onRowClick={s => navigate(`/conversations/${s.session_id}`)}
        emptyText={
          <EmptyState
            icon={<MessagesSquare strokeWidth={1.5} />}
            title="该应用暂无会话记录"
            description="在 Playground 关联此应用对话，或经 API / 嵌入式调用后会出现在这里。"
          />
        }
      />
      {total > pageSize && (
        <div className="border-t border-stone-100 px-4 py-2.5">
          <TablePagination
            page={page}
            pageSize={pageSize}
            total={total}
            onPageChange={setPage}
            onPageSizeChange={s => {
              setPageSize(s);
              setPage(1);
            }}
          />
        </div>
      )}
    </DetailSection>
  );
};
