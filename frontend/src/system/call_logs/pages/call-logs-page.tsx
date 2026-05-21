/** 调用日志查询页 */

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { DataTable, type DataTableColumn } from '@/core/components/common/data-table';
import { PageHeader } from '@/core/components/common/page-header';
import { Badge } from '@/core/components/ui/badge';
import { Input } from '@/core/components/ui/input';
import { Label } from '@/core/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { formatDateTime, formatNumber } from '@/core/lib/format';
import { callLogApi } from '@/system/call_logs/services/call-log';
import type { CallLogItem } from '@/system/call_logs/types/call-log';

export const CallLogsPage = () => {
  const [page, setPage] = useState(1);
  const [appId, setAppId] = useState('');
  const [agentKey, setAgentKey] = useState('');
  const [success, setSuccess] = useState<string>('all');

  const listQ = useQuery({
    queryKey: ['call-logs', page, appId, agentKey, success],
    queryFn: () =>
      callLogApi.list({
        page,
        page_size: 50,
        app_id: appId || undefined,
        agent_key: agentKey || undefined,
        success: success === 'all' ? undefined : success === 'true',
      }),
  });

  const columns: DataTableColumn<CallLogItem>[] = [
    {
      key: 'created_at',
      title: '时间',
      render: l => <span className="text-xs text-stone-500">{formatDateTime(l.created_at)}</span>,
    },
    { key: 'app_id', title: 'app', render: l => <span className="font-mono text-xs">{l.app_id}</span> },
    {
      key: 'agent_key',
      title: 'agent',
      render: l => <span className="font-mono text-xs">{l.agent_key}</span>,
    },
    {
      key: 'status',
      title: '状态',
      render: l =>
        l.success ? (
          <Badge variant="success">成功</Badge>
        ) : (
          <Badge variant="danger">{l.code}</Badge>
        ),
    },
    {
      key: 'duration',
      title: '耗时',
      render: l => <span className="font-mono text-xs">{l.duration_ms} ms</span>,
    },
    {
      key: 'tokens',
      title: 'Token',
      render: l =>
        l.total_tokens ? (
          <span className="font-mono text-xs text-stone-500">
            {formatNumber(l.total_tokens)}
          </span>
        ) : (
          '—'
        ),
    },
    {
      key: 'error',
      title: '错误',
      render: l => (
        <span className="text-xs text-red-600">{l.error_message?.slice(0, 80) || '—'}</span>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title="调用日志" description="实时查询 call_logs（含错误堆栈）" />

      {/* 过滤栏 */}
      <div className="mb-4 grid grid-cols-3 gap-3">
        <div>
          <Label className="text-xs">App ID</Label>
          <Input
            value={appId}
            onChange={e => {
              setAppId(e.target.value);
              setPage(1);
            }}
            placeholder="过滤 app_id"
          />
        </div>
        <div>
          <Label className="text-xs">Agent Key</Label>
          <Input
            value={agentKey}
            onChange={e => {
              setAgentKey(e.target.value);
              setPage(1);
            }}
            placeholder="过滤 agent_key"
          />
        </div>
        <div>
          <Label className="text-xs">状态</Label>
          <Select
            value={success}
            onValueChange={v => {
              setSuccess(v);
              setPage(1);
            }}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部</SelectItem>
              <SelectItem value="true">仅成功</SelectItem>
              <SelectItem value="false">仅失败</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <DataTable
        columns={columns}
        data={listQ.data?.items || []}
        loading={listQ.isLoading}
        pagination={{ page, pageSize: 50, total: listQ.data?.total || 0, onPageChange: setPage }}
      />
    </div>
  );
};
