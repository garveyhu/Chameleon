/** 右侧 Inspector —— 按 node type 渲染表单编辑 spec.data
 *
 * 现阶段每种 node 手写表单（5 类 + noop）；JSONSchemaForm 串通后改成 schema 驱动（PR 后续）。
 */

import { Trash2 } from 'lucide-react';

import { Input } from '@/core/components/ui/input';
import { Textarea } from '@/core/components/ui/textarea';
import { AgentDebateForm } from '@/system/graphs/components/agent-debate-form';
import type { GraphNodeType, NodeSpec } from '@/system/graphs/types/graph';

interface Props {
  node: NodeSpec | null;
  onChange: (next: NodeSpec) => void;
  onDelete: () => void;
}

export const NodeInspector = ({ node, onChange, onDelete }: Props) => {
  if (!node) {
    return (
      <aside className="flex h-full w-72 shrink-0 flex-col gap-2 border-l border-stone-200/70 bg-warm-2/40 p-3 text-[12px] text-stone-500">
        <div className="font-medium text-stone-700">未选中节点</div>
        <div className="text-[11px] leading-snug">
          点画布上一个节点查看 / 编辑其配置；或从左侧 palette 拖一个新节点到画布。
        </div>
      </aside>
    );
  }

  const setData = (patch: Record<string, unknown>) =>
    onChange({ ...node, data: { ...(node.data || {}), ...patch } });

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col gap-3 overflow-y-auto border-l border-stone-200/70 bg-warm-2/40 p-3">
      <header className="flex items-center justify-between">
        <div>
          <div className="text-[10.5px] uppercase tracking-wider text-stone-500">
            {node.type}
          </div>
          <div className="font-mono text-[11px] text-stone-700">
            id={node.id}
          </div>
        </div>
        {node.type !== 'start' && (
          <button
            type="button"
            onClick={onDelete}
            title="删除节点"
            className="rounded p-1 text-stone-400 hover:bg-rose-50 hover:text-rose-600"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </header>

      <Field label="显示名">
        <Input
          value={node.name || ''}
          onChange={e => onChange({ ...node, name: e.target.value })}
          className="h-7 text-[12px]"
        />
      </Field>

      <DataForm type={node.type} data={node.data || {}} onPatch={setData} />
    </aside>
  );
};


// ── per-type forms ───────────────────────────────────────


const DataForm = ({
  type,
  data,
  onPatch,
}: {
  type: GraphNodeType;
  data: Record<string, unknown>;
  onPatch: (patch: Record<string, unknown>) => void;
}) => {
  if (type === 'llm') {
    return (
      <>
        <Field label="model_name（留空走默认）">
          <Input
            value={(data.model_name as string) || ''}
            onChange={e => onPatch({ model_name: e.target.value || undefined })}
            placeholder="qwen-plus / gpt-4o-mini …"
            className="h-7 text-[12px]"
          />
        </Field>
        <Field label="system_prompt">
          <Textarea
            value={(data.system_prompt as string) || ''}
            onChange={e => onPatch({ system_prompt: e.target.value || undefined })}
            rows={3}
            className="text-[12px]"
          />
        </Field>
        <Field label="prompt_template（可选；用 {field} 引 input）">
          <Textarea
            value={(data.prompt_template as string) || ''}
            onChange={e => onPatch({ prompt_template: e.target.value || undefined })}
            rows={2}
            placeholder="Q: {query}\nA:"
            className="font-mono text-[12px]"
          />
        </Field>
        <Field label="temperature">
          <Input
            type="number"
            min={0}
            max={2}
            step={0.1}
            value={(data.temperature as number | undefined) ?? ''}
            onChange={e =>
              onPatch({
                temperature: e.target.value
                  ? Number(e.target.value)
                  : undefined,
              })
            }
            className="h-7 text-[12px]"
          />
        </Field>
      </>
    );
  }

  if (type === 'kb') {
    return (
      <>
        <Field label="kb_key（必填）">
          <Input
            value={(data.kb_key as string) || ''}
            onChange={e => onPatch({ kb_key: e.target.value })}
            placeholder="smoke / my-kb"
            className="h-7 font-mono text-[12px]"
          />
        </Field>
        <Field label="top_k">
          <Input
            type="number"
            min={1}
            value={(data.top_k as number | undefined) ?? 5}
            onChange={e => onPatch({ top_k: Number(e.target.value) })}
            className="h-7 text-[12px]"
          />
        </Field>
        <Field label="min_score">
          <Input
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={(data.min_score as number | undefined) ?? 0}
            onChange={e => onPatch({ min_score: Number(e.target.value) })}
            className="h-7 text-[12px]"
          />
        </Field>
      </>
    );
  }

  if (type === 'tool') {
    return (
      <>
        <Field label="tool_key（P18.2 才可用）">
          <Input
            value={(data.tool_key as string) || ''}
            onChange={e => onPatch({ tool_key: e.target.value })}
            placeholder="http / sql / code_sandbox"
            className="h-7 font-mono text-[12px]"
          />
        </Field>
        <div className="text-[10.5px] leading-snug text-stone-500">
          P18.1：Tool 协议未上线，跑到该节点会 raise NotImplementedError。
        </div>
      </>
    );
  }

  if (type === 'agent_debate') {
    return <AgentDebateForm data={data} onPatch={onPatch} />;
  }

  if (type === 'if_else') {
    const condStr = JSON.stringify(data.condition || {}, null, 2);
    return (
      <>
        <Field label="condition（jsonlogic 风表达式）">
          <Textarea
            value={condStr}
            onChange={e => {
              try {
                const parsed = JSON.parse(e.target.value);
                onPatch({ condition: parsed });
              } catch {
                /* 语法暂时错误时不写回，等用户改完 */
              }
            }}
            rows={8}
            className="font-mono text-[11.5px]"
          />
        </Field>
        <div className="text-[10.5px] leading-snug text-stone-500">
          支持：var / const / == != &gt; &lt; &gt;= &lt;= / and or not
        </div>
      </>
    );
  }

  if (type === 'iteration') {
    return (
      <>
        <JsonField
          label="body（子图 GraphSpec，必填）"
          value={data.body}
          fallback={{ nodes: [], edges: [] }}
          onChange={v => onPatch({ body: v })}
          rows={7}
          hint="对每个 item 跑一遍的子图（含自己的 start/end）"
        />
        <Field label="items_path（可选，从 input 取数组的 dot 路径）">
          <Input
            value={(data.items_path as string) || ''}
            onChange={e => onPatch({ items_path: e.target.value || undefined })}
            placeholder="data.items"
            className="h-7 font-mono text-[12px]"
          />
        </Field>
        <Field label="item_input_key（可选）">
          <Input
            value={(data.item_input_key as string) || ''}
            onChange={e =>
              onPatch({ item_input_key: e.target.value || undefined })
            }
            placeholder="item"
            className="h-7 font-mono text-[12px]"
          />
        </Field>
        <Field label="max_iterations（默认 100，cap 1000）">
          <Input
            type="number"
            min={1}
            max={1000}
            value={(data.max_iterations as number | undefined) ?? 100}
            onChange={e => onPatch({ max_iterations: Number(e.target.value) })}
            className="h-7 text-[12px]"
          />
        </Field>
        <Field label="concurrency（>1 并行，无 early_stop 时）">
          <Input
            type="number"
            min={1}
            value={(data.concurrency as number | undefined) ?? 1}
            onChange={e => onPatch({ concurrency: Number(e.target.value) })}
            className="h-7 text-[12px]"
          />
        </Field>
        <JsonField
          label="early_stop（可选，if_else 表达式；truthy 则停）"
          value={data.early_stop}
          fallback={{}}
          onChange={v => onPatch({ early_stop: v })}
          rows={4}
          hint="设了则强制串行"
        />
      </>
    );
  }

  if (type === 'parallel') {
    return (
      <>
        <JsonField
          label="branches（[{key, body}]，2–20 条，必填）"
          value={data.branches}
          fallback={[{ key: 'a', body: { nodes: [], edges: [] } }]}
          onChange={v => onPatch({ branches: v })}
          rows={8}
          hint="每条 branch 的 body 是独立子图，同一 input fork 后并发跑"
        />
        <Field label="join_strategy">
          <select
            value={(data.join_strategy as string) || 'collect'}
            onChange={e => onPatch({ join_strategy: e.target.value })}
            className="h-7 w-full rounded-md border border-stone-200 bg-white px-2 text-[12px]"
          >
            <option value="collect">collect（等全部成功）</option>
            <option value="merge">merge（浅合并各分支 dict）</option>
            <option value="race">race（最先成功者胜）</option>
          </select>
        </Field>
        <Field label="concurrency（默认 = 分支数）">
          <Input
            type="number"
            min={1}
            value={(data.concurrency as number | undefined) ?? ''}
            onChange={e =>
              onPatch({
                concurrency: e.target.value
                  ? Number(e.target.value)
                  : undefined,
              })
            }
            className="h-7 text-[12px]"
          />
        </Field>
      </>
    );
  }

  if (type === 'human_input') {
    return (
      <>
        <Field label="prompt（给审核人的提示）">
          <Textarea
            value={(data.prompt as string) || ''}
            onChange={e => onPatch({ prompt: e.target.value || undefined })}
            rows={2}
            className="text-[12px]"
          />
        </Field>
        <JsonField
          label="schema（可选，期望输入的 JSON schema）"
          value={data.schema}
          fallback={{}}
          onChange={v => onPatch({ schema: v })}
          rows={4}
          hint="前端据此渲染回填表单"
        />
        <Field label="timeout_seconds（可选，超时未回填则该 run failed）">
          <Input
            type="number"
            min={1}
            value={(data.timeout_seconds as number | undefined) ?? ''}
            onChange={e =>
              onPatch({
                timeout_seconds: e.target.value
                  ? Number(e.target.value)
                  : undefined,
              })
            }
            placeholder="86400"
            className="h-7 text-[12px]"
          />
        </Field>
      </>
    );
  }

  // start / end / noop 无需配置
  return (
    <div className="text-[11.5px] text-stone-500">该节点类型无需配置。</div>
  );
};


/** 嵌套对象/数组字段的 JSON 编辑（与 if_else condition 同套路：语法错时暂不写回）。
 *  iteration.body / parallel.branches 这类子图先用 JSON 配，可视化嵌套编辑后续做。 */
const JsonField = ({
  label,
  value,
  fallback,
  onChange,
  rows = 6,
  hint,
}: {
  label: string;
  value: unknown;
  fallback: unknown;
  onChange: (parsed: unknown) => void;
  rows?: number;
  hint?: string;
}) => (
  <Field label={label}>
    <Textarea
      value={JSON.stringify(value ?? fallback, null, 2)}
      onChange={e => {
        try {
          onChange(JSON.parse(e.target.value));
        } catch {
          /* 语法暂时错误时不写回，等用户改完 */
        }
      }}
      rows={rows}
      className="font-mono text-[11.5px]"
    />
    {hint && (
      <div className="mt-1 text-[10.5px] leading-snug text-stone-500">
        {hint}
      </div>
    )}
  </Field>
);


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
