/** 审计日志查询页 —— waveflow 风格 */

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { History } from 'lucide-react';

import { EmptyState } from '@/core/components/common/empty-state';
import {
  DataTable,
  type DataTableColumn,
  SectionCard,
  TablePagination,
  TableToolbar,
} from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { Input } from '@/core/components/ui/input';
import { StatusBadge, type StatusTone } from '@/core/components/ui/status-badge';
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

/** 动作 → 语义色：增=绿 / 删=红 / 改=蓝 / 登录等=中性 */
const actionTone = (action: string): StatusTone => {
  const a = action.toLowerCase();
  if (/(create|add|invite|register|grant|enable)/.test(a)) return 'success';
  if (/(delete|remove|revoke|disable|ban)/.test(a)) return 'error';
  if (/(update|edit|modify|reset|toggle|config)/.test(a)) return 'info';
  return 'neutral';
};

const BAR_BY_TONE: Record<StatusTone, string> = {
  success: 'bg-emerald-400',
  error: 'bg-red-400',
  warning: 'bg-amber-400',
  info: 'bg-sky-400',
  running: 'bg-sky-400',
  neutral: 'bg-stone-300',
};

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
      width: 156,
      render: a => (
        <span className="tnum font-mono text-[11.5px] text-stone-500">
          {formatDateTime(a.created_at)}
        </span>
      ),
    },
    {
      key: 'action',
      header: '动作',
      width: 132,
      render: a => <StatusBadge tone={actionTone(a.action)}>{a.action}</StatusBadge>,
    },
    {
      key: 'actor',
      header: '操作者',
      width: 156,
      render: a => (
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-stone-100 text-[10px] font-medium text-stone-600">
            {(a.actor_username || '?').slice(0, 1).toUpperCase()}
          </span>
          <span className="truncate text-[12px] text-stone-700">
            {a.actor_username || `#${a.actor_user_id ?? '?'}`}
          </span>
        </div>
      ),
    },
    {
      key: 'resource',
      header: '资源',
      render: a => (
        <div className="flex min-w-0 items-center gap-1.5">
          <Badge variant="outline" className="shrink-0">
            {a.resource_type}
          </Badge>
          {a.resource_id && (
            <span className="truncate font-mono text-[11px] text-stone-500">{a.resource_id}</span>
          )}
        </div>
      ),
    },
    {
      key: 'client',
      header: '客户端',
      width: 200,
      render: a => (
        <div className="min-w-0">
          <div className="tnum font-mono text-[11px] text-stone-600">{a.ip || '—'}</div>
          {a.user_agent && (
            <div className="truncate text-[10px] text-stone-400" title={a.user_agent}>
              {a.user_agent}
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'request_id',
      header: t('table.request_id'),
      width: 132,
      render: a => (
        <span className="tnum block truncate font-mono text-[11px] text-stone-400">
          {a.request_id || '—'}
        </span>
      ),
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
          leftBar={a => BAR_BY_TONE[actionTone(a.action)]}
          emptyText={
            <EmptyState
              icon={<History strokeWidth={1.5} />}
              title={t('empty.audit_logs')}
            />
          }
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
