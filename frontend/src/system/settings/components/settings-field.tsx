/** 单个 setting 字段渲染（按 value_type 分发） */

import { RotateCcw } from 'lucide-react';
import * as React from 'react';

import { Input } from '@/core/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { Switch } from '@/core/components/ui/switch';
import { Tooltip } from '@/core/components/ui/tooltip';
import type { SystemSettingItem } from '@/system/settings/services/settings';

interface SettingsFieldProps {
  item: SystemSettingItem;
  draftValue: unknown;
  onChange: (key: string, value: unknown) => void;
  onReset: (key: string) => void;
  language?: 'zh' | 'en';
}

export const SettingsField: React.FC<SettingsFieldProps> = ({
  item,
  draftValue,
  onChange,
  onReset,
  language = 'zh',
}) => {
  const label = language === 'zh' ? item.description_zh : item.description_en;
  const dirty = draftValue !== item.value;

  const renderControl = () => {
    switch (item.value_type) {
      case 'int':
      case 'float':
        return (
          <Input
            type="number"
            value={String(draftValue ?? '')}
            min={item.min ?? undefined}
            max={item.max ?? undefined}
            step={item.value_type === 'int' ? 1 : 0.01}
            className="max-w-[240px]"
            onChange={e => {
              const raw = e.target.value;
              if (raw === '') {
                onChange(item.key, null);
                return;
              }
              onChange(item.key, item.value_type === 'int' ? parseInt(raw, 10) : parseFloat(raw));
            }}
          />
        );
      case 'bool':
        return (
          <Switch
            checked={!!draftValue}
            onCheckedChange={v => onChange(item.key, v)}
          />
        );
      case 'select':
        return (
          <Select value={String(draftValue ?? '')} onValueChange={v => onChange(item.key, v)}>
            <SelectTrigger className="max-w-[240px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {item.select_options.map(opt => (
                <SelectItem key={opt} value={opt}>
                  {opt}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        );
      default:
        return (
          <Input
            type="text"
            value={String(draftValue ?? '')}
            className="max-w-[400px]"
            onChange={e => onChange(item.key, e.target.value)}
          />
        );
    }
  };

  return (
    <div className="flex items-start justify-between gap-6 border-b border-stone-100 py-3 last:border-b-0">
      <div className="flex-1">
        <div className="flex items-center gap-2 text-[13px] font-medium text-stone-800">
          {label || item.key}
          {dirty ? (
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-500" title="未保存" />
          ) : null}
        </div>
        <div className="mt-0.5 font-mono text-[10.5px] text-stone-400">
          {item.key} · 默认 {String(item.default ?? '—')}
        </div>
      </div>
      <div className="flex items-center gap-2">
        {renderControl()}
        <Tooltip content="重置为默认值">
          <button
            type="button"
            onClick={() => onReset(item.key)}
            className="rounded p-1 text-stone-400 hover:bg-stone-100 hover:text-stone-700"
            aria-label="重置"
          >
            <RotateCcw className="h-3.5 w-3.5" strokeWidth={1.75} />
          </button>
        </Tooltip>
      </div>
    </div>
  );
};
