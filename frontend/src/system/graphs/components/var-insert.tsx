/** 变量插入助手 —— 在 LLM prompt 字段下方一键插入系统变量引用（Dify {{#...#}} 语法）
 *
 * 系统变量任意节点可用；上游节点输出用 {{#节点id.字段#}}（节点 id 见 inspector 顶部）。
 */

interface SysVar {
  token: string;
  label: string;
  desc: string;
}

const SYS_VARS: SysVar[] = [
  { token: '{{#sys.query#}}', label: 'sys.query', desc: '本轮用户输入' },
  { token: '{{#sys.history#}}', label: 'sys.history', desc: '对话历史（多轮记忆）' },
  { token: '{{#sys.conversation_id#}}', label: 'sys.conversation_id', desc: '会话 ID' },
];

export const VarInsert = ({ onInsert }: { onInsert: (token: string) => void }) => (
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
    <span className="text-[10px] text-stone-400">
      · 上游节点：{'{{#节点id.字段#}}'}
    </span>
  </div>
);
