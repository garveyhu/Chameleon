/** 应用详情「会话」tab —— 该应用的会话列表（ChatSession 维度）。
 *
 * 数据源 callLogApi.listSessions（按 agent_key 过滤）。展示会话标题/轮次/终端用户/
 * 最后消息时间；点行进会话详情（/conversations/{id}，渲染多模态消息含图片/视频）。
 * 顶部「在会话账本中查看全部」跳 /sessions?agent_key=X。
 */
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, MessagesSquare } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';

import { EmptyState } from '@/core/components/common/empty-state';
import { DataTable, type DataTableColumn } from '@/core/components/table';
import { formatDateTime } from '@/core/lib/format';
import { ChannelLabel } from '@/system/call_logs/components/ledger-badges';
import { callLogApi } from '@/system/call_logs/services/call-log';
import type { SessionItem } from '@/system/call_logs/types/call-log';

interface Props {
  agentKey: string;
}

const RECENT_SIZE = 20;

export const AgentSessionsTab = ({ agentKey }: Props) => {
  const navigate = useNavigate();

  const listQ = useQuery({
    queryKey: ['agent-session-list', agentKey],
    queryFn: () =>
      callLogApi.listSessions({ page: 1, page_size: RECENT_SIZE, agent_key: agentKey }),
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
          <div className="truncate text-[12.5px] text-stone-800">
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
      render: s => (s.channel ? <ChannelLabel channel={s.channel} /> : <span className="text-stone-400">—</span>),
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
      width: 130,
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
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-[12px] text-stone-500">
          近期会话{total > 0 ? ` · 共 ${total} 个` : ''}
        </span>
        <Link
          to={`/sessions?agent_key=${encodeURIComponent(agentKey)}`}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12px] font-medium text-blue-600 transition hover:bg-blue-50"
        >
          在会话账本中查看全部
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>

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
            description="在 Playground 关联此应用对话，或经 API / 嵌入式调用后，会话会出现在这里。"
          />
        }
      />
    </div>
  );
};
