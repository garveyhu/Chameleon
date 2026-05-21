/** 审计日志查询页 —— waveflow 风格 */

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  DataTable,
  type DataTableColumn,
  SectionCard,
  TablePagination,
  TableToolbar,
} from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { Input } from '@/core/components/ui/input';
import { formatDateTime } from '@/core/lib/format';
import { get } from '@/core/lib/request';
import type { PageResult } from '@/core/types/api';

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
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [resourceInput, setResourceInput] = useState('');
  const [actionInput, setActionInput] = useState('');
  const [resourceType, setResourceType] = useState('');
  const [action, setAction] = useState('');

  const listQ = useQuery({
    queryKey: ['audit-logs', page, pageSize, resourceType, action],
    queryFn: () =>
      get<PageResult<AuditLogItem>>('/v1/admin/audit-logs', {
        params: {
          page,
          page_size: pageSize,
          resource_type: resourceType || undefined,
          action: action || undefined,
        },
      }),
  });

  const columns: DataTableColumn<AuditLogItem>[] = [
    {
      key: 'created_at',
      header: '时间',
      width: 160,
      render: a => <span className="tnum font-mono text-[11.5px] text-stone-500">{formatDateTime(a.created_at)}</span>,
    },
    {
      key: 'actor',
      header: '操作者',
      width: 120,
      render: a => <span className="font-mono text-[11.5px] text-stone-700">{a.actor_username || '?'}</span>,
    },
    {
      key: 'action',
      header: '动作',
      width: 100,
      render: a => <Badge variant="primary">{a.action}</Badge>,
    },
    {
      key: 'resource',
      header: '资源',
      render: a => (
        <span className="font-mono text-[11.5px] text-stone-700">
          {a.resource_type}
          {a.resource_id && `:${a.resource_id}`}
        </span>
      ),
    },
    { key: 'ip', header: t('table.ip'), width: 130, render: a => <span className="font-mono text-[11.5px] tnum">{a.ip || '—'}</span> },
    {
      key: 'request_id',
      header: t('table.request_id'),
      width: 140,
      render: a => <span className="font-mono text-[11.5px] text-stone-400 tnum truncate">{a.request_id || '—'}</span>,
    },
  ];

  return (
    <div>
      <SectionCard>
        <TableToolbar
          title={t('page.audit_logs_title')}
          extra={
            <>
              <Input
                className="!h-7 !text-[12px]"
                style={{ maxWidth: 150 }}
                placeholder="资源类型"
                value={resourceInput}
                onChange={e => setResourceInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    setResourceType(resourceInput);
                    setPage(1);
                  }
                }}
              />
              <Input
                className="!h-7 !text-[12px]"
                style={{ maxWidth: 130 }}
                placeholder="动作"
                value={actionInput}
                onChange={e => setActionInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    setAction(actionInput);
                    setPage(1);
                  }
                }}
              />
            </>
          }
        />
        <DataTable
          columns={columns}
          rows={listQ.data?.items || []}
          rowKey="id"
          loading={listQ.isLoading}
          emptyText={t('empty.audit_logs')}
        />
        <TablePagination
          page={page}
          pageSize={pageSize}
          total={listQ.data?.total || 0}
          onPageChange={setPage}
          onPageSizeChange={s => {
            setPageSize(s);
            setPage(1);
          }}
        />
      </SectionCard>
    </div>
  );
};
