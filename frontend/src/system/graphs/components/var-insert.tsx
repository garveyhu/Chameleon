/** 变量插入助手 —— 紧凑的「{x} 变量」下拉（Dify 套路）
 *
 * 一个下拉里给：系统变量（sys.query/history/conversation_id）+ 按上游节点分组的输出引用。
 * 选中即把 {{#...#}} token 追加到目标字段。取代过去一排 chip + 单独节点下拉的杂乱布局。
 */
import { Braces, ChevronDown } from 'lucide-react';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/core/components/ui/dropdown-menu';

interface SysVar {
  token: string;
  label: string;
  desc: string;
}

export interface NodeVarOption {
  token: string;
  /** 字段名（如 answer / joined_context） */
  label: string;
  /** 所属上游节点名（用于分组展示）；缺省则不分组 */
  group?: string;
}

const SYS_VARS: SysVar[] = [
  { token: '{{#sys.query#}}', label: 'sys.query', desc: '本轮输入' },
  { token: '{{#sys.history#}}', label: 'sys.history', desc: '对话历史' },
  { token: '{{#sys.conversation_id#}}', label: 'sys.conversation_id', desc: '会话 ID' },
];

interface Props {
  onInsert: (token: string) => void;
  /** 上游节点输出可选项（按 group=节点名 分组）；空则只给系统变量 */
  nodeVars?: NodeVarOption[];
}

export const VarInsert = ({ onInsert, nodeVars }: Props) => {
  const groups = groupVars(nodeVars ?? []).filter(g => g.group);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          title="插入变量引用"
          className="inline-flex items-center gap-1 rounded-md border border-stone-200 bg-white px-1.5 py-0.5 text-[10.5px] text-stone-500 transition hover:bg-stone-50 hover:text-stone-700"
        >
          <Braces className="h-3 w-3" />
          变量
          <ChevronDown className="h-3 w-3 opacity-50" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-72 w-56 overflow-y-auto">
        <DropdownMenuLabel className="text-[10px] tracking-wide text-stone-400 uppercase">
          系统变量
        </DropdownMenuLabel>
        {SYS_VARS.map(v => (
          <DropdownMenuItem
            key={v.token}
            onSelect={() => onInsert(v.token)}
            className="text-[11px]"
          >
            <span className="font-mono">{v.label}</span>
            <span className="ml-auto pl-3 text-[9.5px] text-stone-400">{v.desc}</span>
          </DropdownMenuItem>
        ))}
        {groups.map(g => (
          <div key={g.group}>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="text-[10px] tracking-wide text-stone-400 uppercase">
              {g.group}
            </DropdownMenuLabel>
            {g.items.map(o => (
              <DropdownMenuItem
                key={o.token}
                onSelect={() => onInsert(o.token)}
                className="font-mono text-[11px]"
              >
                {o.label}
              </DropdownMenuItem>
            ))}
          </div>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

/** 按 group（上游节点名）聚合变量选项，保持出现顺序 */
function groupVars(vars: NodeVarOption[]): { group?: string; items: NodeVarOption[] }[] {
  const out: { group?: string; items: NodeVarOption[] }[] = [];
  const idx = new Map<string, number>();
  for (const v of vars) {
    const key = v.group ?? '';
    let i = idx.get(key);
    if (i === undefined) {
      i = out.length;
      idx.set(key, i);
      out.push({ group: v.group, items: [] });
    }
    out[i].items.push(v);
  }
  return out;
}
