/** 调用日志查询页 —— waveflow 风格 */

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { FileText } from 'lucide-react';

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
import { formatDateTime, formatNumber } from '@/core/lib/format';
import { TraceDrawer } from '@/system/call_logs/components/trace-drawer';
import { callLogApi } from '@/system/call_logs/services/call-log';
import type { CallLogItem } from '@/system/call_logs/types/call-log';

export const CallLogsPage = () => {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [appIdInput, setAppIdInput] = useState('');
  const [agentKeyInput, setAgentKeyInput] = useState('');
  const [appId, setAppId] = useState('');
  const [agentKey, setAgentKey] = useState('');
  const [success, setSuccess] = useState<string>('all');
  const [traceLog, setTraceLog] = useState<CallLogItem | null>(null);

  const listQ = useQuery({
    queryKey: ['call-logs', page, pageSize, appId, agentKey, success],
    queryFn: () =>
      callLogApi.list({
        page,
        page_size: pageSize,
        app_id: appId || undefined,
        agent_key: agentKey || undefined,
        success: success === 'all' ? undefined : success === 'true',
      }),
  });

  const columns: DataTableColumn<CallLogItem>[] = [
    {
      key: 'created_at',
      header: '时间',
      width: 160,
      render: l => <span className="tnum font-mono text-[11.5px] text-stone-500">{formatDateTime(l.created_at)}</span>,
    },
    {
      key: 'app_id',
      header: t('table.app_key'),
      width: 140,
      render: l => <span className="font-mono text-[11.5px] text-stone-700">{l.app_id}</span>,
    },
    {
      key: 'agent_key',
      header: t('table.agent_key'),
      width: 160,
      render: l => <span className="font-mono text-[11.5px] text-stone-700">{l.agent_key}</span>,
    },
    {
      key: 'status',
      header: t('common.status'),
      width: 80,
      render: l =>
        l.success ? (
          <Badge variant="success">成功</Badge>
        ) : (
          <Badge variant="danger">{l.code}</Badge>
        ),
    },
    {
      key: 'duration',
      header: t('table.duration'),
      width: 90,
      align: 'right',
      render: l => <span className="tnum font-mono text-[11.5px]">{l.duration_ms} ms</span>,
    },
    {
      key: 'tokens',
      header: t('table.tokens'),
      width: 90,
      align: 'right',
      render: l =>
        l.total_tokens ? (
          <span className="tnum font-mono text-[11.5px] text-stone-500">
            {formatNumber(l.total_tokens)}
          </span>
        ) : (
          <span className="text-stone-400">—</span>
        ),
    },
    {
      key: 'error',
      header: '错误',
      render: l => (
        <span className="text-[11.5px] text-red-600">{l.error_message?.slice(0, 80) || '—'}</span>
      ),
    },
  ];

  return (
    <div>
      <SectionCard>
        <TableToolbar
          title={t('page.call_logs_title')}
          filters={[
            {
              value: success,
              onChange: v => {
                setSuccess(v);
                setPage(1);
              },
              placeholder: t('common.status'),
              options: [
                { value: 'true', label: '仅成功' },
                { value: 'false', label: '仅失败' },
              ],
              width: 100,
            },
          ]}
          extra={
            <>
              <Input
                className="!h-7 !text-[12px]"
                style={{ maxWidth: 140 }}
                placeholder="app_id"
                value={appIdInput}
                onChange={e => setAppIdInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    setAppId(appIdInput);
                    setPage(1);
                  }
                }}
              />
              <Input
                className="!h-7 !text-[12px]"
                style={{ maxWidth: 160 }}
                placeholder="agent_key"
                value={agentKeyInput}
                onChange={e => setAgentKeyInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    setAgentKey(agentKeyInput);
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
          onRowClick={setTraceLog}
          emptyText={
            <EmptyState
              icon={<FileText strokeWidth={1.5} />}
              title={t('empty.call_logs')}
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
      <TraceDrawer callLog={traceLog} onClose={() => setTraceLog(null)} />
    </div>
  );
};
