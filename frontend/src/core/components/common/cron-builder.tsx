/** Cron 触发周期可视化生成器 —— 频率 + 时间 + 周/日 选择，自动拼 5 段 cron。
 *  受控组件：value 是 cron 字符串，onChange 吐新表达式；无法解析的表达式落「自定义」原样编辑。 */

import { useMemo, useState } from 'react';

import { cn } from '@/core/lib/cn';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { Input } from '@/core/components/ui/input';

type Freq = 'hourly' | 'daily' | 'weekly' | 'monthly' | 'custom';

const FREQ_OPTIONS: { value: Freq; label: string }[] = [
  { value: 'hourly', label: '每小时' },
  { value: 'daily', label: '每天' },
  { value: 'weekly', label: '每周' },
  { value: 'monthly', label: '每月' },
  { value: 'custom', label: '自定义表达式' },
];

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

interface Parsed {
  freq: Freq;
  minute: number;
  hour: number;
  weekday: number;
  dom: number;
}

/** 把 cron 反解析成 builder 态；非整点/复杂表达式落 custom。 */
const parseCron = (expr: string): Parsed => {
  const def: Parsed = { freq: 'daily', minute: 0, hour: 9, weekday: 1, dom: 1 };
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return { ...def, freq: 'custom' };
  const [m, h, dom, mon, dow] = parts;
  const isNum = (s: string) => /^\d+$/.test(s);
  // 月份必须是 *，否则太复杂走 custom
  if (mon !== '*') return { ...def, freq: 'custom' };
  if (h === '*' && isNum(m) && dom === '*' && dow === '*') {
    return { ...def, freq: 'hourly', minute: Number(m) };
  }
  if (!isNum(m) || !isNum(h)) return { ...def, freq: 'custom' };
  const minute = Number(m);
  const hour = Number(h);
  if (dom === '*' && dow === '*') return { ...def, freq: 'daily', minute, hour };
  if (dom === '*' && isNum(dow)) {
    return { ...def, freq: 'weekly', minute, hour, weekday: Number(dow) };
  }
  if (isNum(dom) && dow === '*') {
    return { ...def, freq: 'monthly', minute, hour, dom: Number(dom) };
  }
  return { ...def, freq: 'custom' };
};

/** builder 态 → cron 表达式 */
const buildCron = (p: Parsed): string => {
  const m = p.minute;
  const h = p.hour;
  switch (p.freq) {
    case 'hourly':
      return `${m} * * * *`;
    case 'daily':
      return `${m} ${h} * * *`;
    case 'weekly':
      return `${m} ${h} * * ${p.weekday}`;
    case 'monthly':
      return `${m} ${h} ${p.dom} * *`;
    default:
      return '';
  }
};

/** 人类可读摘要 */
const describe = (p: Parsed, raw: string): string => {
  const hh = String(p.hour).padStart(2, '0');
  const mm = String(p.minute).padStart(2, '0');
  switch (p.freq) {
    case 'hourly':
      return `每小时的第 ${p.minute} 分钟触发`;
    case 'daily':
      return `每天 ${hh}:${mm} 触发`;
    case 'weekly':
      return `每${WEEKDAYS[p.weekday]} ${hh}:${mm} 触发`;
    case 'monthly':
      return `每月 ${p.dom} 号 ${hh}:${mm} 触发`;
    default:
      return raw.trim() ? `自定义：${raw.trim()}` : '请填写 cron 表达式';
  }
};

interface Props {
  value: string;
  onChange: (cron: string) => void;
}

export const CronBuilder = ({ value, onChange }: Props) => {
  // 用 value 初始化一次 builder 态；之后由内部交互驱动（value 反解析只在挂载时）。
  const [state, setState] = useState<Parsed>(() => parseCron(value));
  const [customText, setCustomText] = useState(() =>
    parseCron(value).freq === 'custom' ? value : '',
  );

  const patch = (next: Partial<Parsed>) => {
    const merged = { ...state, ...next };
    setState(merged);
    if (merged.freq !== 'custom') onChange(buildCron(merged));
  };

  const summary = useMemo(
    () => describe(state, customText),
    [state, customText],
  );

  const hours = Array.from({ length: 24 }, (_, i) => i);
  const minutes = [0, 5, 10, 15, 20, 30, 45];

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={state.freq}
          onValueChange={v => {
            const freq = v as Freq;
            if (freq === 'custom') {
              setState(s => ({ ...s, freq }));
              const raw = customText || buildCron({ ...state, freq: 'daily' });
              setCustomText(raw);
              onChange(raw);
            } else {
              patch({ freq });
            }
          }}
        >
          <SelectTrigger className="w-[120px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {FREQ_OPTIONS.map(o => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {state.freq === 'weekly' && (
          <Select
            value={String(state.weekday)}
            onValueChange={v => patch({ weekday: Number(v) })}
          >
            <SelectTrigger className="w-[92px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {WEEKDAYS.map((w, i) => (
                <SelectItem key={i} value={String(i)}>
                  {w}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        {state.freq === 'monthly' && (
          <Select
            value={String(state.dom)}
            onValueChange={v => patch({ dom: Number(v) })}
          >
            <SelectTrigger className="w-[92px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Array.from({ length: 31 }, (_, i) => i + 1).map(d => (
                <SelectItem key={d} value={String(d)}>
                  {d} 号
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        {(state.freq === 'daily' ||
          state.freq === 'weekly' ||
          state.freq === 'monthly') && (
          <>
            <Select
              value={String(state.hour)}
              onValueChange={v => patch({ hour: Number(v) })}
            >
              <SelectTrigger className="w-[78px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {hours.map(h => (
                  <SelectItem key={h} value={String(h)}>
                    {String(h).padStart(2, '0')} 时
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="text-stone-400">:</span>
          </>
        )}

        {state.freq !== 'custom' && (
          <Select
            value={String(state.minute)}
            onValueChange={v => patch({ minute: Number(v) })}
          >
            <SelectTrigger className="w-[78px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {minutes.map(m => (
                <SelectItem key={m} value={String(m)}>
                  {String(m).padStart(2, '0')} 分
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      {state.freq === 'custom' && (
        <Input
          value={customText}
          onChange={e => {
            setCustomText(e.target.value);
            onChange(e.target.value);
          }}
          placeholder="* * * * *（分 时 日 月 周）"
          className="font-mono"
        />
      )}

      <div
        className={cn(
          'flex items-center gap-2 text-[11px]',
          state.freq === 'custom' && !customText.trim()
            ? 'text-stone-400'
            : 'text-stone-500',
        )}
      >
        <span>{summary}</span>
        <span className="font-mono text-stone-400">
          {state.freq === 'custom' ? customText.trim() : buildCron(state)}
        </span>
      </div>
    </div>
  );
};
