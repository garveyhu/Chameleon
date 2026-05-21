/** TableToolbar —— 紧凑表格工具栏（复刻 waveflow）
 *
 * 布局：title 左 | search + filters + extra 右
 * 控件高度统一 h-7 紧凑
 */

import { Search } from 'lucide-react';
import * as React from 'react';

import { Input } from '@/core/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from '@/core/components/ui/select';
import { cn } from '@/core/lib/cn';

export interface ToolbarFilterOption {
  value: string;
  label: string;
}

export interface ToolbarFilter {
  /** 当前值，'all' 表示未筛选 */
  value: string;
  onChange: (next: string) => void;
  placeholder: string;
  options: ToolbarFilterOption[];
  /** "全部" label，默认"全部" */
  allLabel?: string;
  /** trigger 宽度，默认 110 */
  width?: number;
}

export interface ToolbarSearch {
  /** 输入框 local state */
  value: string;
  onChange: (next: string) => void;
  /** 回车或点 icon 提交（建议同步 keyword + reset page） */
  onSubmit: (value: string) => void;
  /** 可选：value 不变时强制刷新 */
  onRefresh?: () => void;
  placeholder?: string;
  width?: number;
}

export interface TableToolbarProps {
  /** 左侧标题（如"用户列表"） */
  title?: React.ReactNode;
  search?: ToolbarSearch;
  filters?: ToolbarFilter[];
  /** 右侧 extra（按钮 / 菜单） */
  extra?: React.ReactNode;
  className?: string;
}

export const TableToolbar: React.FC<TableToolbarProps> = ({
  title,
  search,
  filters,
  extra,
  className,
}) => {
  return (
    <div className={cn('mb-2.5 flex items-center gap-2', className)}>
      {title ? <h3 className="text-[13.5px] font-semibold text-stone-900">{title}</h3> : null}

      <div className="ml-auto flex flex-wrap items-center gap-1.5">
        {search ? (
          <div className="relative">
            <button
              type="button"
              title="搜索"
              className="absolute left-1.5 top-1/2 z-10 -translate-y-1/2 rounded p-0.5 text-stone-400 transition hover:bg-stone-100 hover:text-stone-700"
              onClick={() => {
                search.onSubmit(search.value);
                search.onRefresh?.();
              }}
            >
              <Search className="h-3 w-3" />
            </button>
            <Input
              className="!h-7 pl-6 text-[12px]"
              style={{ maxWidth: search.width ?? 180 }}
              placeholder={search.placeholder ?? '搜索'}
              value={search.value}
              onChange={e => search.onChange(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') search.onSubmit(search.value);
              }}
            />
          </div>
        ) : null}

        {(filters ?? []).map((f, idx) => {
          const optLabel = f.options.find(o => o.value === f.value)?.label;
          const triggerText = f.value === 'all' ? f.placeholder : (optLabel ?? f.placeholder);
          return (
            <Select key={idx} value={f.value} onValueChange={f.onChange}>
              <SelectTrigger
                className="!h-7 whitespace-nowrap !text-[12px]"
                style={{ width: f.width ?? 110 }}
              >
                <span className="truncate">{triggerText}</span>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{f.allLabel ?? '全部'}</SelectItem>
                {f.options.map(o => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          );
        })}

        {extra}
      </div>
    </div>
  );
};
