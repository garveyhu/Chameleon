/** 节点面板基建（Dify 套路）—— 可折叠分区 / 字段 / 输出变量只读区
 *
 * 各节点 inspector 共用这套原语，统一「分区 + 字段 + 输出」的高级观感。
 */
import { useState } from 'react';

import { ChevronDown, HelpCircle } from 'lucide-react';

import { cn } from '@/core/lib/cn';
import { VarInsert } from '@/system/graphs/components/var-insert';
import type { NodeVarOption } from '@/system/graphs/components/var-insert';
import { NODE_OUTPUT_FIELDS } from '@/system/graphs/lib/node-meta';
import type { GraphNodeType } from '@/system/graphs/types/graph';

export const Section = ({
  title,
  tip,
  right,
  defaultOpen = true,
  children,
}: {
  title: string;
  tip?: string;
  right?: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-t border-stone-200/60 first:border-t-0">
      <div className="flex items-center gap-1 py-2">
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          className="flex flex-1 items-center gap-1 text-left"
        >
          <ChevronDown
            className={cn('h-3.5 w-3.5 text-stone-400 transition', !open && '-rotate-90')}
          />
          <span className="text-[11.5px] font-medium text-stone-700">{title}</span>
          {tip && (
            <span title={tip} className="inline-flex">
              <HelpCircle className="h-3 w-3 text-stone-300" />
            </span>
          )}
        </button>
        {right}
      </div>
      {open && <div className="space-y-2.5 pb-3">{children}</div>}
    </div>
  );
};

export const PanelField = ({
  label,
  required,
  tip,
  children,
}: {
  label: string;
  required?: boolean;
  tip?: string;
  children: React.ReactNode;
}) => (
  <div>
    <div className="mb-1 flex items-center gap-1">
      <label className="text-[11px] text-stone-600">{label}</label>
      {required && <span className="text-[11px] text-rose-500">*</span>}
      {tip && (
        <span title={tip} className="inline-flex">
          <HelpCircle className="h-3 w-3 text-stone-300" />
        </span>
      )}
    </div>
    {children}
  </div>
);

/** 提示词「消息块」—— 顶栏（标签 + 变量下拉）+ 无边框 textarea（Dify 消息块观感） */
export const PromptField = ({
  label,
  value,
  onChange,
  onInsert,
  nodeVars,
  rows = 4,
  placeholder,
  mono,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  onInsert: (token: string) => void;
  nodeVars?: NodeVarOption[];
  rows?: number;
  placeholder?: string;
  mono?: boolean;
}) => (
  <div className="overflow-hidden rounded-lg border border-stone-200 bg-white transition focus-within:border-stone-300 focus-within:ring-2 focus-within:ring-stone-100">
    <div className="flex items-center justify-between border-b border-stone-100 bg-stone-50/70 px-2 py-1">
      <span className="text-[10px] font-medium tracking-wide text-stone-500 uppercase">
        {label}
      </span>
      <VarInsert onInsert={onInsert} nodeVars={nodeVars} />
    </div>
    <textarea
      value={value}
      onChange={e => onChange(e.target.value)}
      rows={rows}
      placeholder={placeholder}
      className={cn(
        'block w-full resize-y border-0 bg-transparent px-2.5 py-2 text-[12px] leading-relaxed text-stone-800 outline-none placeholder:text-stone-300 focus:ring-0',
        mono && 'font-mono',
      )}
    />
  </div>
);

/** 输出变量只读区 —— 列出该节点会产出的字段，供下游引用（Dify 信号特征） */
export const OutputVarsSection = ({ type }: { type: GraphNodeType }) => {
  const fields = NODE_OUTPUT_FIELDS[type];
  if (!fields || fields.length === 0) return null;
  return (
    <Section title="输出变量" defaultOpen={false}>
      <div className="space-y-1">
        {fields.map(f => (
          <div key={f} className="flex items-center gap-1.5 rounded-md bg-stone-50 px-2 py-1">
            <span className="font-mono text-[10px] text-violet-500">{'{x}'}</span>
            <span className="font-mono text-[11.5px] text-stone-700">{f}</span>
            <span className="ml-auto text-[10px] text-stone-400">变量</span>
          </div>
        ))}
      </div>
    </Section>
  );
};
