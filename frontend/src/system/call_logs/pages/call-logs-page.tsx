/** 调用日志查询页 —— waveflow 风格 */

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';

import { FileText } from 'lucide-react';

import { EmptyState } from '@/core/components/common/empty-state';
import {
  DataTable,
  type DataTableColumn,
  SectionCard,
  TablePagination,
  TableToolbar,
} from '@/core/components/table';
import { Input } from '@/core/components/ui/input';
import { StatusBadge } from '@/core/components/ui/status-badge';
import { formatDateTime, formatDurationMs, formatTokens } from '@/core/lib/format';
import { TraceDrawer } from '@/system/call_logs/components/trace-drawer';
import { callLogApi } from '@/system/call_logs/services/call-log';
import type { CallLogItem } from '@/system/call_logs/types/call-log';

/** 延迟色阶：<1s 静默 / <3s 常规 / <10s 黄 / 更久 红 */
const latencyClass = (ms: number): string =>
  ms < 1000
    ? 'text-stone-500'
    : ms < 3000
      ? 'text-stone-700'
      : ms < 10000
        ? 'text-amber-600'
        : 'text-red-600';

export const CallLogsPage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  // /traces 走 D4 详情页（树 + 甘特）；/call_logs 仍开轻量 drawer
  const isTraceRoute = pathname.startsWith('/traces');
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
      width: 156,
      render: l => (
        <span className="tnum font-mono text-[11.5px] text-stone-500">
          {formatDateTime(l.created_at)}
        </span>
      ),
    },
    {
      key: 'status',
      header: t('common.status'),
      width: 104,
      render: l =>
        l.success ? (
          <StatusBadge tone="success">成功</StatusBadge>
        ) : (
          <StatusBadge tone="error">失败 {l.code}</StatusBadge>
        ),
    },
    {
      key: 'agent_key',
      header: '能力 / 来源',
      render: l => (
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-1.5">
            <span className="truncate font-mono text-[12px] font-medium text-stone-800">
              {l.agent_key}
            </span>
            {l.stream && (
              <span className="shrink-0 rounded bg-stone-100 px-1 py-0.5 text-[9.5px] text-stone-500">
                流式
              </span>
            )}
          </div>
          <div className="truncate font-mono text-[10.5px] text-stone-400">{l.app_id}</div>
          {!l.success && l.error_message && (
            <div className="truncate text-[10.5px] text-red-500" title={l.error_message}>
              {l.error_message}
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'duration',
      header: t('table.duration'),
      width: 96,
      align: 'right',
      render: l => (
        <span className={`tnum font-mono text-[11.5px] ${latencyClass(l.duration_ms)}`}>
          {formatDurationMs(l.duration_ms)}
        </span>
      ),
    },
    {
      key: 'tokens',
      header: t('table.tokens'),
      width: 116,
      align: 'right',
      render: l =>
        l.total_tokens ? (
          <div className="text-right">
            <div className="tnum font-mono text-[11.5px] text-stone-700">
              {formatTokens(l.total_tokens)}
            </div>
            {l.prompt_tokens != null && l.completion_tokens != null && (
              <div className="tnum font-mono text-[10px] text-stone-400">
                ↑{formatTokens(l.prompt_tokens)} ↓{formatTokens(l.completion_tokens)}
              </div>
            )}
          </div>
        ) : (
          <span className="text-stone-400">—</span>
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
          leftBar={l => (l.success ? 'bg-emerald-400' : 'bg-red-400')}
          onRowClick={row =>
            isTraceRoute
              ? navigate(`/traces/${encodeURIComponent(row.request_id)}`)
              : setTraceLog(row)
          }
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
