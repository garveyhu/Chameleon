/** 运行对比矩阵 —— 借鉴 Langfuse：样本行 × 运行列，score 色块热力图。
 *  点任一行（问题或某格）→ 居中弹窗，并排看各运行在该样本上的 预期 / 实际 输出。 */

import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ChevronRight } from 'lucide-react';
import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useRef,
  useState,
} from 'react';

import {
  Modal,
  ModalBody,
  ModalContent,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import { cn } from '@/core/lib/cn';
import { exportImage } from '@/core/lib/dom-export';
import { formatScore, scoreBg } from '@/core/lib/score';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { RunCompareStats } from '@/system/datasets/components/run-compare-stats';
import { datasetApi } from '@/system/datasets/services/dataset';
import type { DatasetRunRow } from '@/system/datasets/types/dataset';
import { shortRunName } from '@/system/datasets/utils/run-name';

const runMean = (r: DatasetRunRow): number | null => {
  const s = r.summary as Record<string, unknown> | null;
  const v = s?.mean_score ?? s?.mean ?? s?.avg_score;
  return typeof v === 'number' ? v : null;
};

// 优先从 {answer/sql/output/...} 取可读文本，否则美化 JSON —— 对比时全文直显。
const PREFER_KEYS = ['answer', 'sql', 'output', 'text', 'content', 'query', 'value'];
const asText = (v: unknown): string => {
  if (v == null) return '—';
  if (typeof v === 'string') return v;
  if (typeof v === 'object') {
    const o = v as Record<string, unknown>;
    for (const k of PREFER_KEYS) {
      if (typeof o[k] === 'string') return o[k] as string;
    }
    return JSON.stringify(v, null, 2);
  }
  return String(v);
};

const OutputBlock = ({ value }: { value: unknown }) => (
  <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded bg-stone-50 p-2 font-mono text-[11.5px] leading-relaxed text-stone-700">
    {asText(value)}
  </pre>
);

export interface RunCompareHandle {
  exportImage: () => Promise<void>;
  exportExcel: () => Promise<void>;
}

interface Props {
  runIds: EntityId[];
  /** 数据集名（导出图片报告头 + 图片/Excel 文件名带上） */
  datasetName?: string;
  /** 导出忙碌态回调（页面头按钮据此置 loading / 禁用） */
  onExportingChange?: (busy: boolean) => void;
}

// 文件名安全化：去掉路径分隔符等
const fileSafe = (s: string) => s.replace(/[\\/:*?"<>|]+/g, '_').trim();

export const RunCompareMatrix = forwardRef<RunCompareHandle, Props>(
  ({ runIds, datasetName, onExportingChange }, ref) => {
  const q = useQuery({
    queryKey: ['ds-compare', [...runIds].sort()],
    queryFn: () => datasetApi.compareRuns(runIds),
    enabled: runIds.length >= 2,
  });
  // 选中的样本行 id（点击即开弹窗对比所有运行）；null = 关闭
  const [selItem, setSelItem] = useState<string | null>(null);
  // 对比统计区默认折叠（多数时候先看逐题热力图，统计按需展开）
  const [statsOpen, setStatsOpen] = useState(false);
  // 导出：截图态（展开统计 + 去裁剪 + 加报告头）
  const [exporting, setExporting] = useState(false);
  const captureRef = useRef<HTMLDivElement>(null);

  const setExp = useCallback(
    (b: boolean) => {
      setExporting(b);
      onExportingChange?.(b);
    },
    [onExportingChange],
  );

  // 导出报告图片：展开统计 + 进入截图态，等图表/分析渲染稳定后截整页 PNG（含得分表）
  const doExportImage = useCallback(async () => {
    if (!q.data) return;
    setStatsOpen(true);
    setExp(true);
    // 双 rAF + 短延时，等 recharts 布局完成 + AI 分析展开
    await new Promise(r =>
      requestAnimationFrame(() => requestAnimationFrame(() => r(null))),
    );
    await new Promise(r => setTimeout(r, 600));
    try {
      if (captureRef.current) {
        const day = new Date().toLocaleDateString('zh-CN').replace(/\//g, '-');
        // 降像素比控制体积；不跳字体内联——否则回退系统字体（更宽）会让图例换行、
        // 整体与网页字体不一致。字体嵌入开销小，节点数才是耗时大头。
        const prefix = datasetName ? `${fileSafe(datasetName)}_` : '';
        await exportImage(captureRef.current, `${prefix}运行对比_${day}.png`, {
          pixelRatio: 1.5,
        });
      }
    } catch {
      toast.error('导出图片失败，请重试');
    } finally {
      setExp(false);
    }
  }, [q.data, setExp, datasetName]);

  // 导出明细数据：逐题 × 各模型（得分 + 输出）为 xlsx
  const doExportExcel = useCallback(async () => {
    if (!q.data) return;
    const { runs, rows } = q.data;
    try {
      const XLSX = await import('xlsx');
      const header = [
        '#',
        '问题',
        '考察点',
        '预期',
        ...runs.flatMap(r => [
          `${shortRunName(r.name)}·得分`,
          `${shortRunName(r.name)}·输出`,
        ]),
      ];
      const aoa: (string | number)[][] = [
        header,
        ...rows.map((row, i) => {
          const base = [
            i + 1,
            row.input_preview ?? '',
            row.note ?? '',
            asText(row.expected_output),
          ];
          const cells = runs.flatMap(r => {
            const c = row.cells[String(r.id)];
            return [c?.score ?? '', c ? asText(c.actual_output) : ''];
          });
          return [...base, ...cells];
        }),
      ];
      const ws = XLSX.utils.aoa_to_sheet(aoa);
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, '运行对比');
      const day = new Date().toLocaleDateString('zh-CN').replace(/\//g, '-');
      const prefix = datasetName ? `${fileSafe(datasetName)}_` : '';
      XLSX.writeFile(wb, `${prefix}运行对比明细_${day}.xlsx`);
    } catch {
      toast.error('导出数据失败，请重试');
    }
  }, [q.data, datasetName]);

  useImperativeHandle(
    ref,
    () => ({ exportImage: doExportImage, exportExcel: doExportExcel }),
    [doExportImage, doExportExcel],
  );

  if (q.isLoading) {
    return (
      <div className="py-8 text-center text-[12px] text-stone-400">
        加载对比…
      </div>
    );
  }
  const data = q.data;
  if (!data) return null;
  const { runs, rows } = data;
  const categories = data.categories;

  const selRow = selItem
    ? rows.find(r => String(r.dataset_item_id) === selItem)
    : null;

  const today = new Date().toLocaleDateString('zh-CN');

  return (
    <div className="space-y-3">
      {/* 截图区：报告头（仅导出）+ 对比统计 + 得分表。透明容器，仅作导出取景边界，
          让对比统计与表格在视觉上是两个独立的块（导出时 exportImage 自动铺白底）。 */}
      <div ref={captureRef} className="space-y-3">
        {exporting && (
          <div className="border-b border-stone-200 pb-2.5">
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-[14px] font-semibold text-stone-800">
                运行对比报告
                {datasetName && (
                  <span className="ml-1.5 text-[12px] font-normal text-stone-500">
                    · {datasetName}
                  </span>
                )}
              </span>
              <span className="shrink-0 text-[10.5px] text-stone-400">
                {today}
              </span>
            </div>
            <div className="mt-1.5 flex flex-wrap gap-x-2 gap-y-1.5">
              {runs.map(run => {
                const m = runMean(run);
                return (
                  <span
                    key={String(run.id)}
                    className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-md bg-stone-100 px-2 py-0.5 text-[11px] text-stone-600"
                  >
                    {shortRunName(run.name)}
                    <span className="tnum font-semibold text-stone-800">
                      {m != null ? formatScore(m) : '—'}
                    </span>
                  </span>
                );
              })}
            </div>
          </div>
        )}

        <section>
          <button
            type="button"
            onClick={() => setStatsOpen(o => !o)}
            className="flex items-center gap-1 text-[12.5px] font-medium text-stone-800 transition hover:text-stone-900"
          >
            {statsOpen ? (
              <ChevronDown className="h-3.5 w-3.5 text-stone-400" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 text-stone-400" />
            )}
            对比统计
            <span className="ml-1.5 text-[10.5px] font-normal text-stone-400">
              能力雷达 · 分数分布 · 逐题得分 · AI 分析
            </span>
          </button>
          {(statsOpen || exporting) && (
            <div className="mt-2 rounded-lg border border-stone-200 bg-white p-3">
              <RunCompareStats
                runs={runs}
                rows={rows}
                runIds={runIds}
                categories={categories}
                exporting={exporting}
              />
            </div>
          )}
        </section>
        <div
          className={cn(
            'rounded-lg border border-stone-200',
            exporting ? '' : 'overflow-auto',
          )}
        >
        <table className="w-full border-collapse text-[11.5px]">
          <thead>
            <tr className="bg-stone-50">
              <th
                className={cn(
                  'min-w-[220px] border-b border-r border-stone-200 bg-stone-50 px-3 py-2 text-left font-medium text-stone-500',
                  !exporting && 'sticky left-0 z-10',
                )}
              >
                样本 · 预期
              </th>
              {runs.map(run => {
                const m = runMean(run);
                return (
                  <th
                    key={String(run.id)}
                    className="min-w-[116px] border-b border-stone-200 px-3 py-2 text-left font-medium text-stone-600"
                  >
                    <div className="truncate" title={run.name}>
                      {shortRunName(run.name)}
                    </div>
                    <div className="mt-0.5 text-[10px] text-stone-400">
                      均值 {m != null ? formatScore(m) : '—'}
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map(row => {
              const itemId = String(row.dataset_item_id);
              return (
                <tr
                  key={itemId}
                  onClick={() => setSelItem(itemId)}
                  className="cursor-pointer hover:bg-stone-50/60"
                >
                  <td
                    className={cn(
                      'max-w-[260px] border-b border-r border-stone-200 bg-white px-3 py-2 align-top',
                      !exporting && 'sticky left-0 z-10',
                    )}
                  >
                    <div
                      className="truncate text-stone-700"
                      title={row.input_preview ?? ''}
                    >
                      {row.input_preview ?? (
                        <span className="text-stone-300">（无预览）</span>
                      )}
                    </div>
                    {row.expected_output != null && (
                      <div className="mt-0.5 truncate text-[10px] text-stone-400">
                        预期 {JSON.stringify(row.expected_output).slice(0, 40)}
                      </div>
                    )}
                  </td>
                  {runs.map(run => {
                    const runId = String(run.id);
                    const cell = row.cells[runId];
                    return (
                      <td
                        key={runId}
                        className="border-b border-stone-100 px-1.5 py-1.5 align-top"
                      >
                        {cell ? (
                          <div
                            className={cn(
                              'tnum w-full rounded px-2 py-1 text-left',
                              scoreBg(cell.score),
                            )}
                          >
                            {cell.score != null
                              ? formatScore(cell.score)
                              : cell.error
                                ? '错误'
                                : '—'}
                          </div>
                        ) : (
                          <span className="pl-2 text-stone-300">—</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr>
                <td
                  colSpan={runs.length + 1}
                  className="px-3 py-8 text-center text-stone-400"
                >
                  无样本
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
      </div>

      <Modal open={!!selRow} onOpenChange={o => !o && setSelItem(null)}>
        <ModalContent size="xl">
          <ModalHeader>
            <ModalTitle>样本输出对比</ModalTitle>
          </ModalHeader>
          {selRow && (
            <ModalBody className="space-y-3">
              <div>
                <div className="mb-1 text-[10px] font-medium text-stone-400">
                  问题
                </div>
                <div className="text-[12.5px] text-stone-800">
                  {selRow.input_preview ?? '（无预览）'}
                </div>
              </div>
              <div className="rounded-md border border-emerald-200/70 bg-emerald-50/40 p-2.5">
                <div className="mb-1 text-[10px] font-medium text-emerald-700">
                  预期（标准答案）
                </div>
                <OutputBlock value={selRow.expected_output} />
              </div>
              <div
                className="grid gap-3"
                style={{
                  gridTemplateColumns: `repeat(${runs.length}, minmax(0, 1fr))`,
                }}
              >
                {runs.map(run => {
                  const cell = selRow.cells[String(run.id)];
                  return (
                    <div
                      key={String(run.id)}
                      className="flex flex-col rounded-md border border-stone-200 bg-white p-2.5"
                    >
                      <div className="mb-1.5 flex items-center justify-between gap-2">
                        <span
                          className="truncate text-[11.5px] font-medium text-stone-700"
                          title={run.name}
                        >
                          {shortRunName(run.name)}
                        </span>
                        <span
                          className={cn(
                            'shrink-0 rounded px-1.5 py-0.5 text-[11px] tnum',
                            scoreBg(cell?.score ?? null),
                          )}
                        >
                          {cell?.score != null
                            ? formatScore(cell.score)
                            : '无分'}
                        </span>
                      </div>
                      <div className="mb-0.5 text-[10px] text-stone-400">
                        实际输出
                      </div>
                      <OutputBlock value={cell?.actual_output} />
                      {cell?.error != null && (
                        <div className="mt-1.5 text-[10.5px] text-rose-600">
                          错误：{JSON.stringify(cell.error).slice(0, 200)}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </ModalBody>
          )}
        </ModalContent>
      </Modal>
    </div>
  );
  },
);

RunCompareMatrix.displayName = 'RunCompareMatrix';
