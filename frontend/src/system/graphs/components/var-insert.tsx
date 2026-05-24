/** 变量插入助手 —— LLM/模板等字段下方一键插入变量引用（Dify {{#...#}} 语法）
 *
 * 系统变量 chip（任意节点可用）+ 上游节点输出下拉（选 节点.字段 插入 {{#nodeid.field#}}）。
 */

interface SysVar {
  token: string;
  label: string;
  desc: string;
}

export interface NodeVarOption {
  token: string;
  label: string;
}

const SYS_VARS: SysVar[] = [
  { token: '{{#sys.query#}}', label: 'sys.query', desc: '本轮用户输入' },
  { token: '{{#sys.history#}}', label: 'sys.history', desc: '对话历史（多轮记忆）' },
  { token: '{{#sys.conversation_id#}}', label: 'sys.conversation_id', desc: '会话 ID' },
];

interface Props {
  onInsert: (token: string) => void;
  /** 上游节点输出可选项（P5-1 变量选择器）；空则提示手打 */
  nodeVars?: NodeVarOption[];
}

export const VarInsert = ({ onInsert, nodeVars }: Props) => (
  <div className="mt-1 flex flex-wrap items-center gap-1">
    <span className="text-[10px] text-stone-400">插入变量：</span>
    {SYS_VARS.map(v => (
      <button
        key={v.token}
        type="button"
        onClick={() => onInsert(v.token)}
        title={v.desc}
        className="rounded bg-sky-50 px-1.5 py-0.5 font-mono text-[10px] text-sky-700 transition hover:bg-sky-100"
      >
        {v.label}
      </button>
    ))}
    {nodeVars && nodeVars.length > 0 ? (
      <select
        defaultValue=""
        onChange={e => {
          if (e.target.value) {
            onInsert(e.target.value);
            e.target.value = '';
          }
        }}
        title="插入上游节点输出引用"
        className="rounded border border-stone-200 bg-white px-1 py-0.5 font-mono text-[10px] text-stone-600"
      >
        <option value="" disabled>
          上游节点…
        </option>
        {nodeVars.map(o => (
          <option key={o.token} value={o.token}>
            {o.label}
          </option>
        ))}
      </select>
    ) : (
      <span className="text-[10px] text-stone-400">
        · 上游节点：{'{{#节点id.字段#}}'}
      </span>
    )}
  </div>
);
