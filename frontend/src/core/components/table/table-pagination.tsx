/** TablePagination —— 完整翻页（复刻 waveflow）
 *
 * 左：from-to / total + page-size select
 * 右：首页 / 上一页 / 当前页码 / 下一页 / 末页 + 跳至 N 页
 */

import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';
import * as React from 'react';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from '@/core/components/ui/select';
import { cn } from '@/core/lib/cn';

export interface TablePaginationProps {
  page: number;
  pageSize: number;
  total: number;
  pageSizeOptions?: number[];
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  className?: string;
}

const DEFAULT_SIZE_OPTIONS = [10, 20, 50, 100];

export const TablePagination: React.FC<TablePaginationProps> = ({
  page,
  pageSize,
  total,
  pageSizeOptions = DEFAULT_SIZE_OPTIONS,
  onPageChange,
  onPageSizeChange,
  className,
}) => {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const from = total === 0 ? 0 : (safePage - 1) * pageSize + 1;
  const to = Math.min(safePage * pageSize, total);

  const go = (p: number) => {
    const next = Math.min(Math.max(1, p), totalPages);
    if (next !== safePage) onPageChange(next);
  };

  const navBtn = (props: {
    disabled: boolean;
    onClick: () => void;
    title: string;
    children: React.ReactNode;
  }) => (
    <button
      type="button"
      className="rounded p-1 transition hover:bg-stone-100 disabled:opacity-30 disabled:hover:bg-transparent"
      disabled={props.disabled}
      onClick={props.onClick}
      title={props.title}
    >
      {props.children}
    </button>
  );

  return (
    <div
      className={cn(
        'mt-3 flex items-center justify-between text-[11.5px] text-stone-500',
        className,
      )}
    >
      <div className="flex items-center gap-3">
        <span className="tnum">
          {from}–{to} / {total}
        </span>
        <Select value={String(pageSize)} onValueChange={v => onPageSizeChange(Number(v))}>
          <SelectTrigger className="!h-7 !w-auto !min-w-[80px] whitespace-nowrap !text-[11.5px]">
            <span className="whitespace-nowrap">{pageSize} 条/页</span>
          </SelectTrigger>
          <SelectContent>
            {pageSizeOptions.map(n => (
              <SelectItem key={n} value={String(n)}>
                {n} 条/页
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex items-center gap-1">
        {navBtn({
          disabled: safePage <= 1,
          onClick: () => go(1),
          title: '首页',
          children: <ChevronsLeft className="h-3.5 w-3.5" />,
        })}
        {navBtn({
          disabled: safePage <= 1,
          onClick: () => go(safePage - 1),
          title: '上一页',
          children: <ChevronLeft className="h-3.5 w-3.5" />,
        })}
        <span className="tnum px-1 font-mono">
          {safePage} / {totalPages}
        </span>
        {navBtn({
          disabled: safePage >= totalPages,
          onClick: () => go(safePage + 1),
          title: '下一页',
          children: <ChevronRight className="h-3.5 w-3.5" />,
        })}
        {navBtn({
          disabled: safePage >= totalPages,
          onClick: () => go(totalPages),
          title: '末页',
          children: <ChevronsRight className="h-3.5 w-3.5" />,
        })}

        <JumpInput current={safePage} totalPages={totalPages} onJump={go} />
      </div>
    </div>
  );
};

const JumpInput: React.FC<{
  current: number;
  totalPages: number;
  onJump: (page: number) => void;
}> = ({ current, totalPages, onJump }) => {
  const [val, setVal] = React.useState('');
  const [editing, setEditing] = React.useState(false);

  const commit = () => {
    setEditing(false);
    if (val === '') return;
    const n = parseInt(val, 10);
    setVal('');
    if (!Number.isFinite(n)) return;
    const clamped = Math.min(Math.max(1, n), totalPages);
    if (clamped !== current) onJump(clamped);
  };

  return (
    <span className="ml-3 flex items-center gap-1.5 text-stone-500">
      <span>跳至</span>
      <input
        type="text"
        inputMode="numeric"
        value={editing ? val : String(current)}
        onFocus={() => {
          setEditing(true);
          setVal('');
        }}
        onChange={e => setVal(e.target.value.replace(/[^\d]/g, ''))}
        onBlur={commit}
        onKeyDown={e => {
          if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
        }}
        className={cn(
          'h-[22px] w-8 border-0 border-b border-dashed border-stone-300 bg-transparent p-0 text-center',
          'tnum font-mono text-[11.5px] font-medium text-stone-800 outline-none transition',
          'focus:border-solid focus:border-blue-500',
        )}
      />
      <span>页</span>
    </span>
  );
};
