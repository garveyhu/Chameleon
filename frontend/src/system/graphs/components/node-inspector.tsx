/** 右侧 Inspector —— 按 node type 渲染表单编辑 spec.data
 *
 * 现阶段每种 node 手写表单（5 类 + noop）；JSONSchemaForm 串通后改成 schema 驱动（PR 后续）。
 */

import { Trash2 } from 'lucide-react';

import { Input } from '@/core/components/ui/input';
import { Textarea } from '@/core/components/ui/textarea';
import { AgentDebateForm } from '@/system/graphs/components/agent-debate-form';
import { IfElseCondition } from '@/system/graphs/components/if-else-condition';
import { NodeRunResult } from '@/system/graphs/components/node-run-result';
import {
  KbKeyField,
  ModelNameField,
} from '@/system/graphs/components/spec-fields';
import { VarInsert } from '@/system/graphs/components/var-insert';
import type { NodeVarOption } from '@/system/graphs/components/var-insert';
import {
  ParallelBranchesField,
  SubgraphField,
} from '@/system/graphs/components/subgraph-fields';
import type {
  GraphNodeType,
  NodeRunView,
  NodeSpec,
} from '@/system/graphs/types/graph';

/** 各节点类型的输出字段（P5-1 变量选择器据此列出可引用项） */
const NODE_OUTPUT_FIELDS: Partial<Record<GraphNodeType, string[]>> = {
  llm: ['answer'],
  kb: ['joined_context', 'hits', 'query'],
  http: ['status_code', 'body', 'headers'],
  template: ['text'],
  answer: ['answer'],
  if_else: ['branch', 'value'],
  agent_debate: ['answer'],
};

export interface PeerNode {
  id: string;
  label: string;
  type: GraphNodeType;
}

function peerVarOptions(peers: PeerNode[]): NodeVarOption[] {
  return peers.flatMap(p => {
    const fields = NODE_OUTPUT_FIELDS[p.type] ?? ['output'];
    return fields.map(f => ({
      token: `{{#${p.id}.${f}#}}`,
      label: `${p.label}.${f}`,
    }));
  });
}

interface Props {
  node: NodeSpec | null;
  /** 该节点在最近一次运行中的结果（有则在配置下方展示） */
  runView?: NodeRunView;
  /** 同图其它节点（P5-1：变量选择器列出可引用的上游输出） */
  peerNodes?: PeerNode[];
  onChange: (next: NodeSpec) => void;
  onDelete: () => void;
}

export const NodeInspector = ({
  node,
  runView,
  peerNodes,
  onChange,
  onDelete,
}: Props) => {
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

      <DataForm
        key={node.id}
        type={node.type}
        data={node.data || {}}
        onPatch={setData}
        nodeVars={peerVarOptions(peerNodes ?? [])}
      />

      {runView && (
        <div className="mt-1 border-t border-stone-200/70 pt-3">
          <div className="mb-2 text-[10.5px] uppercase tracking-wider text-stone-500">
            运行结果
          </div>
          <NodeRunResult run={runView} />
        </div>
      )}
    </aside>
  );
};


// ── per-type forms ───────────────────────────────────────


const DataForm = ({
  type,
  data,
  onPatch,
  nodeVars,
}: {
  type: GraphNodeType;
  data: Record<string, unknown>;
  onPatch: (patch: Record<string, unknown>) => void;
  nodeVars: NodeVarOption[];
}) => {
  if (type === 'llm') {
    return (
      <>
        <Field label="模型（留空走默认）">
          <ModelNameField
            value={(data.model_name as string) || ''}
            onChange={v => onPatch({ model_name: v || undefined })}
          />
        </Field>
        <Field label="system_prompt">
          <Textarea
            value={(data.system_prompt as string) || ''}
            onChange={e => onPatch({ system_prompt: e.target.value || undefined })}
            rows={3}
            className="text-[12px]"
          />
          <VarInsert
            nodeVars={nodeVars}
            onInsert={t =>
              onPatch({ system_prompt: ((data.system_prompt as string) || '') + t })
            }
          />
        </Field>
        <Field label="prompt_template（可选；{{#sys.query#}} 等变量引用）">
          <Textarea
            value={(data.prompt_template as string) || ''}
            onChange={e => onPatch({ prompt_template: e.target.value || undefined })}
            rows={2}
            placeholder="参考资料 {{#kb1.joined_context#}}\n问题：{{#sys.query#}}"
            className="font-mono text-[12px]"
          />
          <VarInsert
            nodeVars={nodeVars}
            onInsert={t =>
              onPatch({
                prompt_template: ((data.prompt_template as string) || '') + t,
              })
            }
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
        <Field label="知识库（必填）">
          <KbKeyField
            value={(data.kb_key as string) || ''}
            onChange={v => onPatch({ kb_key: v })}
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
    return (
      <IfElseCondition
        value={data.condition}
        onChange={cond => onPatch({ condition: cond })}
      />
    );
  }

  if (type === 'template') {
    return (
      <Field label="模板（{{#sys.query#}} / {{#节点id.字段#}} 引用）">
        <Textarea
          value={(data.template as string) || ''}
          onChange={e => onPatch({ template: e.target.value })}
          rows={5}
          placeholder="参考资料：{{#kb1.joined_context#}}\n\n问题：{{#sys.query#}}"
          className="font-mono text-[12px]"
        />
        <VarInsert
          nodeVars={nodeVars}
          onInsert={t => onPatch({ template: ((data.template as string) || '') + t })}
        />
      </Field>
    );
  }

  if (type === 'http') {
    return (
      <>
        <Field label="method">
          <select
            value={(data.method as string) || 'GET'}
            onChange={e => onPatch({ method: e.target.value })}
            className="h-7 w-full rounded-md border border-stone-200 bg-white px-2 text-[12px]"
          >
            {['GET', 'POST', 'PUT', 'DELETE', 'PATCH'].map(m => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </Field>
        <Field label="url（支持 {{#...#}} 引用）">
          <Input
            value={(data.url as string) || ''}
            onChange={e => onPatch({ url: e.target.value })}
            placeholder="https://api.example.com/q?x={{#sys.query#}}"
            className="h-7 font-mono text-[12px]"
          />
          <VarInsert
            nodeVars={nodeVars}
            onInsert={t => onPatch({ url: ((data.url as string) || '') + t })}
          />
        </Field>
        <JsonField
          label="headers（可选）"
          value={data.headers}
          fallback={{}}
          onChange={v => onPatch({ headers: v })}
          rows={3}
        />
        <Field label="body（可选；POST/PUT/PATCH，支持引用）">
          <Textarea
            value={(data.body as string) || ''}
            onChange={e => onPatch({ body: e.target.value || undefined })}
            rows={3}
            className="font-mono text-[12px]"
          />
          <VarInsert
            nodeVars={nodeVars}
            onInsert={t => onPatch({ body: ((data.body as string) || '') + t })}
          />
        </Field>
        <div className="text-[10.5px] leading-snug text-stone-500">
          默认拒绝内网/环回地址；如确需在 JSON 里加 allow_private:true（SSRF 风险自负）。
        </div>
      </>
    );
  }

  if (type === 'aggregator') {
    return (
      <JsonField
        label="fields（{outKey: 模板}，值用 {{#nodeid.字段#}} 引用）"
        value={data.fields}
        fallback={{ ctx: '{{#kb1.joined_context#}}' }}
        onChange={v => onPatch({ fields: v })}
        rows={6}
        hint="把多个节点的字段聚合成一个干净 dict，供下游引用"
      />
    );
  }

  if (type === 'assign') {
    return (
      <JsonField
        label="assignments（{会话变量名: 模板}）"
        value={data.assignments}
        fallback={{ user_name: '{{#sys.query#}}' }}
        onChange={v => onPatch({ assignments: v })}
        rows={5}
        hint="写会话变量；跨轮用 {{#conversation.变量名#}} 读回（客户端携带）"
      />
    );
  }

  if (type === 'classifier') {
    return (
      <>
        <Field label="模型（留空走默认）">
          <ModelNameField
            value={(data.model_name as string) || ''}
            onChange={v => onPatch({ model_name: v || undefined })}
          />
        </Field>
        <JsonField
          label="categories（[{key, description}]，≥2）"
          value={data.categories}
          fallback={[
            { key: 'tech', description: '技术 / 代码问题' },
            { key: 'other', description: '其它' },
          ]}
          onChange={v => onPatch({ categories: v })}
          rows={6}
          hint="LLM 把问题分类，输出 {category}；下游用 if_else 读 {{#本节点id.category#}} 分流"
        />
      </>
    );
  }

  if (type === 'code') {
    return (
      <>
        <Field label="语言">
          <select
            value={(data.language as string) || 'python'}
            onChange={e => onPatch({ language: e.target.value })}
            className="h-7 w-full rounded-md border border-stone-200 bg-white px-2 text-[12px]"
          >
            <option value="python">python</option>
            <option value="node">node</option>
          </select>
        </Field>
        <Field label="代码（input 经 stdin 传入 JSON；stdout 为 JSON 则进 result）">
          <Textarea
            value={(data.code as string) || ''}
            onChange={e => onPatch({ code: e.target.value })}
            rows={8}
            placeholder={'import sys, json\ndata = json.load(sys.stdin)\nprint(json.dumps({"n": len(str(data))}))'}
            className="font-mono text-[11.5px]"
          />
        </Field>
        <div className="text-[10.5px] leading-snug text-stone-500">
          沙箱执行（docker 优先，dev 兜底 mock）；网络默认禁用。
        </div>
      </>
    );
  }

  if (type === 'answer') {
    return (
      <Field label="回答模板（可选；留空则透传上游答案）">
        <Textarea
          value={(data.answer as string) || ''}
          onChange={e => onPatch({ answer: e.target.value || undefined })}
          rows={4}
          placeholder="{{#chat.answer#}}"
          className="font-mono text-[12px]"
        />
        <VarInsert
          nodeVars={nodeVars}
          onInsert={t => onPatch({ answer: ((data.answer as string) || '') + t })}
        />
        <div className="mt-1 text-[10.5px] leading-snug text-stone-500">
          标记 graph 的最终回答来源；agent 调用时优先用本节点输出。
        </div>
      </Field>
    );
  }

  if (type === 'iteration') {
    return (
      <>
        <SubgraphField
          label="body（对每个 item 跑一遍的子图）"
          title="迭代子图"
          spec={data.body}
          onChange={spec => onPatch({ body: spec })}
          hint="可视化编辑含自己 start/end 的子图"
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
        <ParallelBranchesField
          branches={data.branches}
          onChange={branches => onPatch({ branches })}
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

  if (type === 'start') {
    const suggestions = (data.suggested_questions as string[] | undefined) ?? [];
    return (
      <>
        <Field label="开场白（对话调试 / 聊天开始时展示）">
          <Textarea
            value={(data.opener as string) || ''}
            onChange={e => onPatch({ opener: e.target.value || undefined })}
            rows={2}
            placeholder="你好！我是你的助理，有什么可以帮你？"
            className="text-[12px]"
          />
        </Field>
        <Field label="建议问题（每行一个，点击直接发送）">
          <Textarea
            value={suggestions.join('\n')}
            onChange={e =>
              onPatch({
                suggested_questions: e.target.value
                  .split('\n')
                  .map(s => s.trim())
                  .filter(Boolean),
              })
            }
            rows={3}
            placeholder={'介绍一下你的功能\n帮我写一段文案'}
            className="text-[12px]"
          />
        </Field>
      </>
    );
  }

  // end / noop 无需配置
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
