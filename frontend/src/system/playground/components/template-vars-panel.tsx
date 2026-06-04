/** 模板变量填值面板 —— 派生 System Prompt 里的 {{var}}，每个暴露成一行受控 Input。
 *
 * 变量列表纯派生自 systemPrompt（useMemo，非 state，避免 set-state-in-effect）；
 * 无变量返 null 不渲染。值受控写回 values[name]，发送时由 fillTemplate 替换。
 */

import { useMemo } from 'react';

import { Input } from '@/core/components/ui/input';
import { extractVars } from '@/system/playground/utils/template-vars';

interface Props {
  systemPrompt: string;
  values: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
}

export const TemplateVarsPanel = ({ systemPrompt, values, onChange }: Props) => {
  const vars = useMemo(() => extractVars(systemPrompt), [systemPrompt]);

  if (vars.length === 0) return null;

  const setVar = (name: string, value: string) =>
    onChange({ ...values, [name]: value });

  return (
    <div>
      <label className="mb-1 block text-stone-600">模板变量</label>
      <div className="space-y-1.5">
        {vars.map(name => (
          <div key={name} className="flex items-center gap-2">
            <span className="shrink-0 rounded bg-stone-100 px-1.5 py-0.5 font-mono text-[10.5px] text-stone-600">
              {`{{${name}}}`}
            </span>
            <Input
              value={values[name] ?? ''}
              onChange={e => setVar(name, e.target.value)}
              placeholder="未填，将原样发送"
              className="!h-7 flex-1 text-[12px]"
            />
          </div>
        ))}
      </div>
    </div>
  );
};
