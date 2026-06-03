/** 数据集详情页 —— 样本（items）表 + 采样 / 导入入口（运行 Runs / 对比见 P2） */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Download, Upload } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { DataTable, type DataTableColumn } from '@/core/components/table';
import { Button } from '@/core/components/ui/button';
import { cn } from '@/core/lib/cn';
import { formatDateTime } from '@/core/lib/format';
import { BulkImportModal } from '@/system/datasets/components/bulk-import-modal';
import { SampleFromLogsModal } from '@/system/datasets/components/sample-from-logs-modal';
import { datasetApi } from '@/system/datasets/services/dataset';
import type { DatasetItemRow } from '@/system/datasets/types/dataset';

export const DatasetDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  // ⚠️ dsId 保留 string —— snowflake 64-bit 超 MAX_SAFE_INTEGER，Number() 会精度丢失
  const dsId = id ?? '';
  const qc = useQueryClient();
  const [sampleOpen, setSampleOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  const dsQ = useQuery({
    queryKey: ['datasets', dsId],
    queryFn: () => datasetApi.get(dsId),
    enabled: !!dsId,
  });
  const itemsQ = useQuery({
    queryKey: ['datasets', dsId, 'items'],
    queryFn: () => datasetApi.listItems(dsId, 200),
    enabled: !!dsId,
  });

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: ['datasets', dsId] });
    qc.invalidateQueries({ queryKey: ['datasets', dsId, 'items'] });
  };

  if (!dsId) {
    return <div className="p-6 text-sm text-stone-500">非法的数据集编号</div>;
  }

  const cols: DataTableColumn<DatasetItemRow>[] = [
    {
      key: 'source',
      header: '来源',
      width: 96,
      render: it => {
        const isLog = !!it.source_call_log_id;
        return (
          <span
            className={cn(
              'rounded px-1.5 py-0.5 text-[10.5px]',
              isLog
                ? 'bg-emerald-50 text-emerald-700'
                : 'bg-indigo-50 text-indigo-700',
            )}
          >
            {isLog ? '日志采样' : '手工导入'}
          </span>
        );
      },
    },
    {
      key: 'input',
      header: '输入预览',
      render: it => (
        <span className="truncate font-mono text-[11.5px] text-stone-700">
          {extractPreview(it.input_payload) || '—'}
        </span>
      ),
    },
    {
      key: 'expected',
      header: '预期输出',
      render: it => (
        <span className="truncate text-[11.5px] text-stone-500">
          {it.expected_output
            ? JSON.stringify(it.expected_output).slice(0, 80)
            : '—'}
        </span>
      ),
    },
    {
      key: 'sampled',
      header: '采样时间',
      align: 'right',
      width: 160,
      render: it => (
        <span className="text-[11px] text-stone-500">
          {formatDateTime(String(sampledAt(it)))}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <header className="flex items-center gap-3">
        <Link
          to="/datasets"
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12.5px] text-stone-500 hover:bg-stone-100 hover:text-stone-800"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> 数据集
        </Link>
        <span className="text-stone-300">/</span>
        {dsQ.isLoading ? (
          <span className="text-[12.5px] text-stone-400">加载中…</span>
        ) : dsQ.data ? (
          <div className="flex flex-1 items-baseline gap-2">
            <span className="text-[15px] font-medium text-stone-900">
              {dsQ.data.name}
            </span>
            <span className="text-[11.5px] text-stone-500">
              · {dsQ.data.item_count} 样本
            </span>
            <span className="ml-auto" />
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setImportOpen(true)}
            >
              <Upload className="mr-1 h-3.5 w-3.5" /> 手工导入
            </Button>
            <Button size="sm" onClick={() => setSampleOpen(true)}>
              <Download className="mr-1 h-3.5 w-3.5" /> 从日志采样
            </Button>
          </div>
        ) : (
          <span className="text-[12.5px] text-stone-400">未找到</span>
        )}
      </header>

      <DataTable
        columns={cols}
        rows={itemsQ.data ?? []}
        rowKey="id"
        loading={itemsQ.isLoading}
        emptyText="暂无样本，点右上「从日志采样」或「手工导入」开始"
        minWidth={640}
      />

      {sampleOpen && (
        <SampleFromLogsModal
          datasetId={dsId}
          onClose={() => setSampleOpen(false)}
          onDone={() => {
            refreshAll();
            setSampleOpen(false);
          }}
        />
      )}
      {importOpen && (
        <BulkImportModal
          datasetId={dsId}
          onClose={() => setImportOpen(false)}
          onDone={() => {
            refreshAll();
            setImportOpen(false);
          }}
        />
      )}
    </div>
  );
};

function sampledAt(item: DatasetItemRow): unknown {
  const meta = item.meta as Record<string, unknown> | null;
  return meta?.sampled_at ?? meta?.imported_at ?? item.created_at;
}

function extractPreview(payload: Record<string, unknown>): string {
  for (const v of Object.values(payload)) {
    if (typeof v === 'string') return v.slice(0, 80);
    if (
      v &&
      typeof v === 'object' &&
      'preview' in (v as Record<string, unknown>)
    ) {
      const p = (v as Record<string, unknown>).preview;
      if (typeof p === 'string') return p.slice(0, 80);
    }
  }
  return '';
}
