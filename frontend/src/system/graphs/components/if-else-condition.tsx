/** IfElse 条件编辑 —— 简单模式（单比较 var op const）+ 高级 JSON 兜底
 *
 * 后端表达式（白名单）：
 *   {"op": "==|!=|>|<|>=|<=", "left": {"var": "x.y"}, "right": {"const": v}}
 *   复杂逻辑（and/or/not/嵌套）走高级 JSON。
 *
 * 注意：本组件按 node.id keyed 重挂（见 NodeInspector 的 <DataForm key>），
 * 故可安全用内部 state 持原始输入文本，不与 props 打架。
 */

import { useState } from 'react';

import { Input } from '@/core/components/ui/input';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';

const BINARY_OPS = ['==', '!=', '>', '<', '>=', '<='] as const;
type Op = (typeof BINARY_OPS)[number];

interface Simple {
  field: string;
  op: Op;
  value: string;
}

function toSimple(cond: unknown): Simple | null {
  if (!cond || typeof cond !== 'object') return null;
  const c = cond as Record<string, unknown>;
  const left = c.left as Record<string, unknown> | undefined;
  const right = c.right as Record<string, unknown> | undefined;
  if (
    BINARY_OPS.includes(c.op as Op) &&
    left &&
    typeof left.var === 'string' &&
    right &&
    'const' in right
  ) {
    return { field: left.var, op: c.op as Op, value: formatConst(right.const) };
  }
  return null;
}

function isEmptyCond(cond: unknown): boolean {
  return (
    cond == null ||
    (typeof cond === 'object' && Object.keys(cond as object).length === 0)
  );
}

function parseConst(text: string): unknown {
  const t = text.trim();
  if (t === 'true') return true;
  if (t === 'false') return false;
  if (t !== '' && !Number.isNaN(Number(t))) return Number(t);
  return text;
}

function formatConst(v: unknown): string {
  return typeof v === 'string' ? v : JSON.stringify(v);
}

function buildCondition(s: Simple): unknown {
  return {
    op: s.op,
    left: { var: s.field },
    right: { const: parseConst(s.value) },
  };
}

interface Props {
  value: unknown;
  onChange: (cond: unknown) => void;
}

export const IfElseCondition = ({ value, onChange }: Props) => {
  const initial = toSimple(value);
  const [mode, setMode] = useState<'simple' | 'json'>(() =>
    initial || isEmptyCond(value) ? 'simple' : 'json',
  );
  const [field, setField] = useState(initial?.field ?? '');
  const [op, setOp] = useState<Op>(initial?.op ?? '==');
  const [valText, setValText] = useState(initial?.value ?? '');

  const emit = (next: Partial<Simple>) => {
    const s: Simple = { field, op, value: valText, ...next };
    onChange(buildCondition(s));
  };

  const switchToSimple = () => {
    const s = toSimple(value);
    if (s) {
      setField(s.field);
      setOp(s.op);
      setValText(s.value);
    }
    setMode('simple');
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5">
        <label className="flex-1 text-[11px] text-stone-600">条件</label>
        <ModeTab active={mode === 'simple'} onClick={switchToSimple}>
          简单
        </ModeTab>
        <ModeTab active={mode === 'json'} onClick={() => setMode('json')}>
          高级 JSON
        </ModeTab>
      </div>

      {mode === 'simple' ? (
        <>
          <div className="flex items-center gap-1.5">
            <Input
              value={field}
              onChange={e => {
                setField(e.target.value);
                emit({ field: e.target.value });
              }}
              placeholder="字段 (var)，如 user.score"
              className="h-7 flex-1 font-mono text-[12px]"
            />
            <select
              value={op}
              onChange={e => {
                setOp(e.target.value as Op);
                emit({ op: e.target.value as Op });
              }}
              className="h-7 rounded-md border border-stone-200 bg-white px-1.5 text-[12px]"
            >
              {BINARY_OPS.map(o => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </div>
          <Input
            value={valText}
            onChange={e => {
              setValText(e.target.value);
              emit({ value: e.target.value });
            }}
            placeholder="比较值（数字 / true / false / 文本）"
            className="h-7 font-mono text-[12px]"
          />
          <div className="text-[10.5px] leading-snug text-stone-500">
            取 input 字段与一个常量比较；truthy 走 true 分支。复杂逻辑（and/or/not、
            嵌套）请切「高级 JSON」。
          </div>
        </>
      ) : (
        <>
          <Textarea
            value={JSON.stringify(value ?? {}, null, 2)}
            onChange={e => {
              try {
                onChange(JSON.parse(e.target.value));
              } catch {
                /* 语法暂时错误时不写回，等用户改完 */
              }
            }}
            rows={8}
            className="font-mono text-[11.5px]"
          />
          <div className="text-[10.5px] leading-snug text-stone-500">
            {'{"op":"and","left":…,"right":…}'} · var / const · == != &gt; &lt;
            &gt;= &lt;= / and or not
          </div>
        </>
      )}
    </div>
  );
};

const ModeTab = ({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) => (
  <button
    type="button"
    onClick={onClick}
    className={cn(
      'rounded px-1.5 py-0.5 text-[10.5px] transition',
      active
        ? 'bg-amber-100 text-amber-700'
        : 'text-stone-400 hover:bg-stone-100 hover:text-stone-600',
    )}
  >
    {children}
  </button>
);
