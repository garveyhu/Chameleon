/** AgentDebate 节点 Inspector 表单 —— P20.4 PR #57
 *
 * 编辑 spec.data：
 *   - agents: string[]    至少 2 个；按顺序映射 proposer / critic / [judge] / 额外 critic
 *   - max_rounds: int     [1, 10]
 *   - early_stop_on: 'consensus' | 'max_rounds'
 *   - timeout_total_sec: int >= 1
 *   - total_budget_tokens: int >= 100（可选，缺省后端算）
 */

import { useQuery } from '@tanstack/react-query';
import { ArrowDown, ArrowUp, GripVertical, Plus, X } from 'lucide-react';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/core/components/ui/dropdown-menu';
import { Input } from '@/core/components/ui/input';
import { agentApi } from '@/system/agents/services/agent';

const MAX_ROUNDS_CAP = 10;

interface Props {
  data: Record<string, unknown>;
  onPatch: (patch: Record<string, unknown>) => void;
}

export const AgentDebateForm = ({ data, onPatch }: Props) => {
  const agents = (data.agents as string[] | undefined) ?? [];
  const maxRounds = (data.max_rounds as number | undefined) ?? 5;
  const earlyStop =
    (data.early_stop_on as string | undefined) ?? 'consensus';
  const timeoutSec =
    (data.timeout_total_sec as number | undefined) ?? 120;
  const budget = data.total_budget_tokens as number | undefined;

  const agentsQ = useQuery({
    queryKey: ['agents', 'all-enabled-for-debate'],
    queryFn: () => agentApi.list({ enabled: true }),
  });
  const available = (agentsQ.data ?? []).map(a => a.agent_key);
  const unselected = available.filter(k => !agents.includes(k));

  const addAgent = (key: string) => {
    if (!key || agents.includes(key)) return;
    onPatch({ agents: [...agents, key] });
  };

  const removeAt = (idx: number) => {
    onPatch({ agents: agents.filter((_, i) => i !== idx) });
  };

  const moveAt = (idx: number, delta: -1 | 1) => {
    const next = idx + delta;
    if (next < 0 || next >= agents.length) return;
    const copy = [...agents];
    [copy[idx], copy[next]] = [copy[next], copy[idx]];
    onPatch({ agents: copy });
  };

  return (
    <div className="space-y-3">
      <div>
        <label className="mb-1 block text-[11px] text-stone-600">
          参与 agents（顺序：proposer → critic → judge → 额外 critic）
        </label>
        <div className="space-y-1 rounded-md border border-stone-200 bg-white p-1.5">
          {agents.length === 0 ? (
            <div className="px-1 py-2 text-center text-[11px] text-stone-400">
              至少选择 2 个 agent
            </div>
          ) : (
            agents.map((key, idx) => (
              <AgentRow
                key={`${key}-${idx}`}
                idx={idx}
                total={agents.length}
                agentKey={key}
                onRemove={() => removeAt(idx)}
                onMoveUp={() => moveAt(idx, -1)}
                onMoveDown={() => moveAt(idx, 1)}
              />
            ))
          )}
        </div>
        <div className="mt-1">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                disabled={unselected.length === 0 || agentsQ.isLoading}
                className="inline-flex h-7 items-center gap-1 rounded-md border border-stone-200 bg-white px-2 text-[12px] text-stone-700 transition hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Plus className="h-3 w-3" />
                {agentsQ.isLoading
                  ? '加载中…'
                  : unselected.length === 0
                    ? '全部已加入'
                    : '添加 agent'}
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="start"
              className="max-h-64 overflow-y-auto"
            >
              {unselected.map(k => (
                <DropdownMenuItem
                  key={k}
                  onSelect={() => addAgent(k)}
                  className="font-mono text-[12px]"
                >
                  {k}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Field label="max_rounds (1-10)">
          <Input
            type="number"
            min={1}
            max={MAX_ROUNDS_CAP}
            value={maxRounds}
            onChange={e =>
              onPatch({
                max_rounds: Math.max(
                  1,
                  Math.min(MAX_ROUNDS_CAP, Number(e.target.value) || 1),
                ),
              })
            }
            className="h-7 text-[12px]"
          />
        </Field>
        <Field label="timeout (s)">
          <Input
            type="number"
            min={1}
            value={timeoutSec}
            onChange={e =>
              onPatch({
                timeout_total_sec: Math.max(1, Number(e.target.value) || 1),
              })
            }
            className="h-7 text-[12px]"
          />
        </Field>
      </div>

      <Field label="early_stop_on">
        <div className="flex gap-1.5">
          {(['consensus', 'max_rounds'] as const).map(opt => (
            <button
              key={opt}
              type="button"
              onClick={() => onPatch({ early_stop_on: opt })}
              className={
                'flex-1 rounded-md border px-2 py-1 text-[11.5px] transition ' +
                (earlyStop === opt
                  ? 'border-fuchsia-300 bg-fuchsia-50 text-fuchsia-700'
                  : 'border-stone-200 bg-white text-stone-600 hover:bg-stone-50')
              }
            >
              {opt}
            </button>
          ))}
        </div>
      </Field>

      <Field label="total_budget_tokens（可选；缺省按 rounds × agents × 2000）">
        <Input
          type="number"
          min={100}
          value={budget ?? ''}
          placeholder="例如 30000"
          onChange={e =>
            onPatch({
              total_budget_tokens: e.target.value
                ? Math.max(100, Number(e.target.value))
                : undefined,
            })
          }
          className="h-7 text-[12px]"
        />
      </Field>

      <div className="rounded-md bg-fuchsia-50/60 px-2 py-1.5 text-[10.5px] leading-snug text-fuchsia-700">
        红线：max_rounds ≤ 10；超时返当前最佳；budget 跨 agent 共享，耗尽即停。
      </div>
    </div>
  );
};

interface AgentRowProps {
  idx: number;
  total: number;
  agentKey: string;
  onRemove: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}

const AgentRow = ({
  idx,
  total,
  agentKey,
  onRemove,
  onMoveUp,
  onMoveDown,
}: AgentRowProps) => {
  const role =
    idx === 0
      ? 'proposer'
      : idx === 1
        ? 'critic'
        : idx === 2
          ? 'judge'
          : `critic+${idx - 1}`;
  return (
    <div className="flex items-center gap-1 rounded px-1.5 py-1 text-[11.5px] hover:bg-stone-50">
      <GripVertical className="h-3 w-3 text-stone-300" />
      <span className="font-mono text-[10px] uppercase text-fuchsia-600">
        {role}
      </span>
      <span className="ml-1 flex-1 truncate font-mono text-stone-700">
        {agentKey}
      </span>
      <button
        type="button"
        onClick={onMoveUp}
        disabled={idx === 0}
        className="rounded p-0.5 text-stone-400 hover:bg-stone-100 hover:text-stone-700 disabled:opacity-30"
      >
        <ArrowUp className="h-3 w-3" />
      </button>
      <button
        type="button"
        onClick={onMoveDown}
        disabled={idx === total - 1}
        className="rounded p-0.5 text-stone-400 hover:bg-stone-100 hover:text-stone-700 disabled:opacity-30"
      >
        <ArrowDown className="h-3 w-3" />
      </button>
      <button
        type="button"
        onClick={onRemove}
        className="rounded p-0.5 text-stone-400 hover:bg-rose-50 hover:text-rose-600"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
};

const Field = ({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) => (
  <div>
    <label className="mb-1 block text-[11px] text-stone-600">{label}</label>
    {children}
  </div>
);
