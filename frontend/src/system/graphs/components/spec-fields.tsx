/** 节点配置里的「资源选择」字段 —— 把 kb_key / model_name 从裸文本框换成下拉，
 *  拉真实 KB / 模型列表，免去手记 key。值仍按后端契约写回（kb_key / model code）。 */

import { useQuery } from '@tanstack/react-query';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { kbApi } from '@/system/kbs/services/kb';
import { modelApi } from '@/system/models/services/model';

const NONE = '__none__'; // Radix Select.Item 不允许空字符串 value，用哨兵代表「空」

interface SelectOption {
  value: string;
  label: string;
  hint?: string;
}

interface ResourceSelectProps {
  value: string;
  onChange: (v: string) => void;
  options: SelectOption[];
  placeholder?: string;
  /** 传则在顶部加一个「清空 / 默认」项（写回空串） */
  noneLabel?: string;
  loading?: boolean;
}

export const ResourceSelect = ({
  value,
  onChange,
  options,
  placeholder,
  noneLabel,
  loading,
}: ResourceSelectProps) => {
  // 当前值不在列表里（例如已删 / 手填的旧值）也保留为一项，避免静默丢失
  const known = options.some(o => o.value === value);
  const merged =
    value && !known
      ? [...options, { value, label: value, hint: '当前值（不在列表）' }]
      : options;

  return (
    <Select
      value={value ? value : NONE}
      onValueChange={v => onChange(v === NONE ? '' : v)}
    >
      <SelectTrigger className="h-7 text-[12px]">
        <SelectValue placeholder={loading ? '加载中…' : placeholder} />
      </SelectTrigger>
      <SelectContent>
        {noneLabel && (
          <SelectItem value={NONE} className="text-[12px]">
            {noneLabel}
          </SelectItem>
        )}
        {merged.map(o => (
          <SelectItem key={o.value} value={o.value} className="text-[12px]">
            <span className="font-mono">{o.label}</span>
            {o.hint && (
              <span className="ml-1.5 text-[10px] text-stone-400">{o.hint}</span>
            )}
          </SelectItem>
        ))}
        {!loading && merged.length === 0 && (
          <div className="px-2 py-1.5 text-[11px] text-stone-400">暂无可选项</div>
        )}
      </SelectContent>
    </Select>
  );
};

export const KbKeyField = ({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) => {
  const q = useQuery({
    queryKey: ['kbs', 'select'],
    queryFn: () => kbApi.list({ page: 1, page_size: 100 }),
  });
  const options = (q.data?.items ?? []).map(k => ({
    value: k.kb_key,
    label: k.name || k.kb_key,
    hint: k.name ? k.kb_key : undefined,
  }));
  return (
    <ResourceSelect
      value={value}
      onChange={onChange}
      options={options}
      loading={q.isLoading}
      placeholder="选择知识库"
    />
  );
};

export const ModelNameField = ({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) => {
  const q = useQuery({
    queryKey: ['models', 'chat', 'select'],
    queryFn: () => modelApi.list({ kind: 'chat' }),
  });
  const options = (q.data ?? [])
    .filter(m => m.enabled)
    .map(m => ({
      value: m.code,
      label: m.code,
      hint: m.provider_code ?? undefined,
    }));
  return (
    <ResourceSelect
      value={value}
      onChange={onChange}
      options={options}
      loading={q.isLoading}
      noneLabel="（留空 · 走默认模型）"
      placeholder="走默认模型"
    />
  );
};
