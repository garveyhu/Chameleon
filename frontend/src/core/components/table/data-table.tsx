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

  loading?: boolean;
  emptyText?: React.ReactNode;
  emptyExtra?: React.ReactNode;

  rowClassName?: (row: T, index: number) => string | undefined;
  /** 每行左侧 4px 状态条 */
  leftBar?: (row: T) => string | undefined;
  /** 整行点击；设置后行加 cursor-pointer */
  onRowClick?: (row: T, index: number) => void;

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
  emptyText = '暂无数据',
  emptyExtra,
  rowClassName,
  leftBar,
  onRowClick,
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
  const [hasMounted, setHasMounted] = React.useState(false);
  React.useEffect(() => {
    setHasMounted(true);
  }, []);
  const empty = rows.length === 0 && !loading && hasMounted;
  const isPlaceholder = (loading || !hasMounted) && rows.length === 0;
  // 400ms 延迟：接口 ≤ 400ms 返回时直接出数据，不闪一下 skeleton
  const showSkeleton = useDelayedFlag(isPlaceholder, 400);

  return (
    <div className={cn('overflow-hidden rounded-lg border border-stone-200/60', className)}>
      <table className="w-full table-fixed">
        <colgroup>
          {hasLeftBar ? <col style={{ width: 4 }} /> : null}
          {columns.map(c => (
            <col key={c.key} style={c.width ? { width: c.width } : undefined} />
          ))}
        </colgroup>
        <thead className="bg-[var(--color-warm-2)]/40">
          <tr className="text-[10.5px] uppercase tracking-wider text-stone-500">
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
                    'px-3 py-2 font-medium',
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
        <tbody className="divide-y divide-stone-100 text-[12.5px]">
          {isPlaceholder ? (
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
                  <td key={c.key} className="px-3 py-2.5">
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
                    'group hover:bg-stone-50/60',
                    onRowClick && 'cursor-pointer',
                    rowClassName?.(row, idx),
                  )}
                  onClick={onRowClick ? () => onRowClick(row, idx) : undefined}
                >
                  {hasLeftBar ? (
                    <td className="p-0">
                      <div className={cn('h-10 w-1', bar ?? 'bg-transparent')} />
                    </td>
                  ) : null}
                  {columns.map(c => (
                    <td
                      key={c.key}
                      className={cn(
                        'px-3 py-2.5',
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
