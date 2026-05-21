/** 审计日志查询页 */

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { DataTable, type DataTableColumn } from '@/core/components/common/data-table';
import { PageHeader } from '@/core/components/common/page-header';
import { Badge } from '@/core/components/ui/badge';
import { Input } from '@/core/components/ui/input';
import { Label } from '@/core/components/ui/label';
import { get } from '@/core/lib/request';
import type { PageResult } from '@/core/types/api';
import { formatDateTime } from '@/core/lib/format';

interface AuditLogItem {
  id: number;
  actor_user_id: number | null;
  actor_username: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  ip: string | null;
  user_agent: string | null;
  request_id: string | null;
  created_at: string;
}

export const AuditLogsPage = () => {
  const [page, setPage] = useState(1);
  const [resourceType, setResourceType] = useState('');
  const [action, setAction] = useState('');

  const listQ = useQuery({
    queryKey: ['audit-logs', page, resourceType, action],
    queryFn: () =>
      get<PageResult<AuditLogItem>>('/v1/admin/audit-logs', {
        params: {
          page,
          page_size: 50,
          resource_type: resourceType || undefined,
          action: action || undefined,
        },
      }),
  });

  const columns: DataTableColumn<AuditLogItem>[] = [
    {
      key: 'created_at',
      title: '时间',
      render: a => <span className="text-xs text-stone-500">{formatDateTime(a.created_at)}</span>,
    },
    {
      key: 'actor',
      title: '操作者',
      render: a => <span className="font-mono">{a.actor_username || '?'}</span>,
    },
    { key: 'action', title: '动作', render: a => <Badge variant="primary">{a.action}</Badge> },
    {
      key: 'resource',
      title: '资源',
      render: a => (
        <span className="font-mono text-xs">
          {a.resource_type}
          {a.resource_id && `:${a.resource_id}`}
        </span>
      ),
    },
    { key: 'ip', title: 'IP', render: a => a.ip || '—' },
    {
      key: 'request_id',
      title: '请求 ID',
      render: a => <span className="font-mono text-xs text-stone-400">{a.request_id || '—'}</span>,
    },
  ];

  return (
    <div>
      <PageHeader title="审计日志" description="所有 admin 写操作的痕迹" />
      <div className="mb-4 grid grid-cols-2 gap-3">
        <div>
          <Label className="text-xs">资源类型</Label>
          <Input
            value={resourceType}
            onChange={e => {
              setResourceType(e.target.value);
              setPage(1);
            }}
            placeholder="users / agents / ..."
          />
        </div>
        <div>
          <Label className="text-xs">动作</Label>
          <Input
            value={action}
            onChange={e => {
              setAction(e.target.value);
              setPage(1);
            }}
            placeholder="create / update / delete ..."
          />
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
