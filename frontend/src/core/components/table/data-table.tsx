/** DataTable —— waveflow 风格表格主体
 *
 * 设计要点：
 *   - wrapper: rounded-lg border-stone-200/60（透明边）overflow-hidden
 *   - thead bg-warm-2/40 暖底，th text-[10.5px] uppercase tracking-wider text-stone-500
 *   - tbody divide-stone-100 + text-[12.5px]
 *   - row hover stone-50/60
 *   - skeleton placeholder 8 行 + 200ms 延迟翻转避免闪烁
 *   - leftBar 4px 状态条（可选）
 *   - 支持点击表头排序
 */

import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';
import * as React from 'react';

import { useDelayedFlag } from '@/core/hooks/use-delayed-flag';
import { cn } from '@/core/lib/cn';

export type SortOrder = 'asc' | 'desc';

export interface DataTableColumn<T> {
  /** 唯一 key（sortable=true 时同时作为排序键） */
  key: string;
  /** 表头内容 */
  header: React.ReactNode;
  /** 列宽（px），不传则自适应 */
  width?: number;
  /** 单元格渲染 */
  render: (row: T, index: number) => React.ReactNode;
  /** 文本对齐 */
  align?: 'left' | 'right' | 'center';
  /** 表头是否可点击排序 */
  sortable?: boolean;
  /** 单元格 className */
  cellClassName?: string;
  /** 表头 className */
  headerClassName?: string;
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  rows: T[];
  rowKey: keyof T | ((row: T) => React.Key);

  sortKey?: string | null;
  sortOrder?: SortOrder;
  onSortChange?: (key: string, order: SortOrder) => void;

  /** 首次加载 / 无数据时的 loading（触发骨架占位）；已有数据的重查请用 refreshing */
  loading?: boolean;
  /**
   * 热刷新（已有数据时的重查，如翻页 / 改筛选）：不替换数据为骨架，
   * 仅顶部滑动进度条 + body 降透明，静默换页。react-query 接 isFetching 即可
   * （配合 placeholderData: keepPreviousData 保留上一页数据）。未传时 loading 在
   * 「已有数据」场景也折进来，让只传 loading 的页面零改动也吃到静默换页。
   */
  refreshing?: boolean;
  emptyText?: React.ReactNode;
  emptyExtra?: React.ReactNode;

  rowClassName?: (row: T, index: number) => string | undefined;
  /** 每行左侧 4px 状态条 */
  leftBar?: (row: T) => string | undefined;
  /** 整行点击；设置后行加 cursor-pointer */
  onRowClick?: (row: T, index: number) => void;

  /**
   * 横向滚动：列总宽超出容器时左右滑动查看，而非压缩列宽（小屏友好）。
   * 开启时所有列建议给定 width，表格按列宽求和取 min-w-max。
   */
  scrollX?: boolean;

  /**
   * 兼顾大小屏的自适应宽度：表格 w-full 撑满容器（大屏不留空白），同时设最小宽度
   * minWidth，容器窄于它时横向滚动而非压缩列宽（小屏）。无固定 width 的列吃掉余量、
   * 等分扩展。设置 minWidth 时自动开启横向滚动，无需再传 scrollX。
   */
  minWidth?: number;

  className?: string;
}

const alignClass = {
  left: 'text-left',
  right: 'text-right',
  center: 'text-center',
};

function SortIndicator({ active, order }: { active: boolean; order: SortOrder }) {
  if (!active) return <ArrowUpDown className="h-3 w-3 text-stone-300" />;
  return order === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  sortKey,
  sortOrder = 'asc',
  onSortChange,
  loading,
  refreshing,
  emptyText = '暂无数据',
  emptyExtra,
  rowClassName,
  leftBar,
  onRowClick,
  scrollX,
  minWidth,
  className,
}: DataTableProps<T>) {
  const getKey = React.useCallback(
    (row: T, idx: number): React.Key => {
      if (typeof rowKey === 'function') return rowKey(row);
      const v = row[rowKey];
      if (v === null || v === undefined) return idx;
      return v as unknown as React.Key;
    },
    [rowKey],
  );

  const handleSort = (col: DataTableColumn<T>) => {
    if (!col.sortable || !onSortChange) return;
    if (sortKey === col.key) {
      onSortChange(col.key, sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      onSortChange(col.key, 'asc');
    }
  };

  const hasLeftBar = !!leftBar;
  const totalCols = columns.length + (hasLeftBar ? 1 : 0);
  const empty = rows.length === 0 && !loading;
  const isPlaceholder = !!loading && rows.length === 0;
  // 200ms 内回数据则全程透明占位（不闪 skeleton）；显形后至少留 400ms，避免"刚亮就被顶掉"
  const showSkeleton = useDelayedFlag(isPlaceholder, 200, 400);
  const renderSkeleton = isPlaceholder || showSkeleton;
  // 热刷新 overlay：已有数据时的重查（翻页 / 改筛选）→ 顶部进度条 + body 降透明，不替换数据。
  // 延迟 250ms（快查询静默）+ 显形后至少 400ms（慢查询不瞬灭），双阈值消除"翻页闪一下"。
  const busy = !!refreshing || !!loading;
  const showOverlay = useDelayedFlag(busy && !isPlaceholder && rows.length > 0, 250, 400);

  // minWidth 自带横向滚动语义；任一开启即允许 x 轴溢出
  const overflowX = scrollX || minWidth != null;

  return (
    <div
      className={cn(
        'relative rounded-lg border border-stone-200/60',
        overflowX ? 'overflow-x-auto' : 'overflow-hidden',
        className,
      )}
    >
      {showOverlay ? (
        <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-[2px] overflow-hidden bg-stone-200/30">
          <div
            className="h-full"
            style={{
              background:
                'linear-gradient(90deg, transparent 0%, #3b82f6 40%, #2563eb 60%, transparent 100%)',
              animation: 'global-progress 1.1s ease-in-out infinite',
            }}
          />
        </div>
      ) : null}
      <table
        className={cn('table-fixed', scrollX && minWidth == null ? 'min-w-max' : 'w-full')}
        style={minWidth != null ? { minWidth } : undefined}
      >
        <colgroup>
          {hasLeftBar ? <col style={{ width: 4 }} /> : null}
          {columns.map(c => (
            <col key={c.key} style={c.width ? { width: c.width } : undefined} />
          ))}
        </colgroup>
        <thead className="border-b border-stone-200/70">
          <tr className="text-[11px] font-medium text-stone-400">
            {hasLeftBar ? <th className="p-0" /> : null}
            {columns.map(c => {
              const active = c.sortable && sortKey === c.key;
              const headerNode =
                c.sortable && onSortChange ? (
                  <button
                    type="button"
                    onClick={() => handleSort(c)}
                    className="inline-flex items-center gap-1 hover:text-stone-900"
                  >
                    {c.header}
                    <SortIndicator active={!!active} order={sortOrder} />
                  </button>
                ) : (
                  c.header
                );
              return (
                <th
                  key={c.key}
                  className={cn(
                    'px-3 py-2.5 font-medium',
                    alignClass[c.align ?? 'left'],
                    c.headerClassName,
                  )}
                >
                  {headerNode}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody
          className={cn(
            'divide-y divide-stone-100 text-[12.5px] transition-opacity duration-200',
            showOverlay && 'pointer-events-none opacity-50',
          )}
        >
          {renderSkeleton ? (
            Array.from({ length: 8 }).map((_, i) => (
              <tr
                key={`skl-${i}`}
                className={cn(
                  'transition-opacity duration-150',
                  showSkeleton ? 'opacity-100' : 'opacity-0',
                )}
              >
                {hasLeftBar ? (
                  <td className="p-0">
                    <div className="h-10 w-1 bg-transparent" />
                  </td>
                ) : null}
                {columns.map(c => (
                  <td key={c.key} className="px-3 py-3">
                    <div
                      className="skeleton h-2 rounded-full"
                      style={{ width: `${40 + ((i * 7 + c.key.length) % 50)}%` }}
                    />
                  </td>
                ))}
              </tr>
            ))
          ) : empty ? (
            <tr>
              <td colSpan={totalCols} className="py-8 text-center text-stone-400">
                <div className="flex flex-col items-center gap-2">
                  <div>{emptyText}</div>
                  {emptyExtra ? <div>{emptyExtra}</div> : null}
                </div>
              </td>
            </tr>
          ) : (
            rows.map((row, idx) => {
              const bar = leftBar?.(row);
              return (
                <tr
                  key={getKey(row, idx)}
                  className={cn(
                    'group transition-colors hover:bg-stone-50',
                    onRowClick && 'cursor-pointer',
                    rowClassName?.(row, idx),
                  )}
                  onClick={onRowClick ? () => onRowClick(row, idx) : undefined}
                >
                  {hasLeftBar ? (
                    <td className="relative p-0">
                      <span
                        className={cn(
                          'absolute inset-y-0 left-0 w-1',
                          bar ?? 'bg-transparent',
                        )}
                      />
                    </td>
                  ) : null}
                  {columns.map(c => (
                    <td
                      key={c.key}
                      className={cn(
                        'px-3 py-3',
                        alignClass[c.align ?? 'left'],
                        c.cellClassName,
                      )}
                    >
                      {c.render(row, idx)}
                    </td>
                  ))}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
