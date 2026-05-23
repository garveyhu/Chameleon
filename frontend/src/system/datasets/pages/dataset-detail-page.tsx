/** Dataset 详情页 —— items 表 + 采样 / import 入口（P21.1 PR #61） */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Download, Upload } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { SectionCard } from '@/core/components/table';
import { Button } from '@/core/components/ui/button';
import { cn } from '@/core/lib/cn';
import { formatDateTime } from '@/core/lib/format';
import { BulkImportModal } from '@/system/datasets/components/bulk-import-modal';
import { SampleFromLogsModal } from '@/system/datasets/components/sample-from-logs-modal';
import { datasetApi } from '@/system/datasets/services/dataset';
import type { DatasetItemRow } from '@/system/datasets/types/dataset';

export const DatasetDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const dsId = id ? Number(id) : 0;
  const qc = useQueryClient();
  const [sampleOpen, setSampleOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  const dsQ = useQuery({
    queryKey: ['datasets', dsId],
    queryFn: () => datasetApi.get(dsId),
    enabled: dsId > 0,
  });

  const itemsQ = useQuery({
    queryKey: ['datasets', dsId, 'items'],
    queryFn: () => datasetApi.listItems(dsId, 200),
    enabled: dsId > 0,
  });

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: ['datasets', dsId] });
    qc.invalidateQueries({ queryKey: ['datasets', dsId, 'items'] });
  };

  if (!dsId) {
    return (
      <SectionCard>
        <div className="p-6 text-sm text-stone-500">非法的 dataset 编号</div>
      </SectionCard>
    );
  }

  return (
    <div className="space-y-3">
      <header className="flex items-center gap-3">
        <Link
          to="/datasets"
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12.5px] text-stone-500 hover:bg-stone-100 hover:text-stone-800"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Datasets
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
              · {dsQ.data.item_count} items
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

      <SectionCard className="!p-0">
        <table className="w-full text-[12.5px]">
          <thead className="bg-warm-2/40 text-[11px] text-stone-500">
            <tr>
              <th className="px-3 py-2 text-left">来源</th>
              <th className="px-3 py-2 text-left">input preview</th>
              <th className="px-3 py-2 text-left">expected</th>
              <th className="px-3 py-2 text-right">采样时间</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {(itemsQ.data ?? []).map(it => (
              <ItemRow key={String(it.id)} item={it} />
            ))}
            {itemsQ.data?.length === 0 && (
              <tr>
                <td
                  colSpan={4}
                  className="px-3 py-12 text-center text-[12px] text-stone-400"
                >
                  暂无 items；点右上「采样」或「导入」开始
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </SectionCard>

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

const ItemRow = ({ item }: { item: DatasetItemRow }) => {
  const source =
    item.source_call_log_id
      ? 'call_log'
      : ((item.meta as Record<string, unknown> | null)?.source as
          | string
          | undefined) ?? 'manual';
  const preview = extractPreview(item.input_payload);
  const expectedText = item.expected_output
    ? JSON.stringify(item.expected_output).slice(0, 80)
    : '—';
  const sampledAt =
    (item.meta as Record<string, unknown> | null)?.sampled_at ??
    (item.meta as Record<string, unknown> | null)?.imported_at ??
    item.created_at;

  return (
    <tr className="hover:bg-warm-2/30">
      <td className="px-3 py-2">
        <span
          className={cn(
            'rounded px-1.5 py-0.5 text-[10.5px] font-mono uppercase',
            source === 'call_log'
              ? 'bg-emerald-50 text-emerald-700'
              : 'bg-indigo-50 text-indigo-700',
          )}
        >
          {source}
        </span>
      </td>
      <td className="px-3 py-2 font-mono text-[11.5px] text-stone-700">
        {preview || '—'}
      </td>
      <td className="px-3 py-2 text-[11.5px] text-stone-500">
        {expectedText}
      </td>
      <td className="px-3 py-2 text-right text-[11px] text-stone-500">
        {formatDateTime(String(sampledAt))}
      </td>
    </tr>
  );
};

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
