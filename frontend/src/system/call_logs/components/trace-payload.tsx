/** Trace 输入/输出渲染：结构化 messages → 系统(参考资料/提示词) / 历史对话 / 本轮输入 分组，
 *  输出带高亮竖条。可切原始 JSON。纯解析在 trace-parse.ts。 */

import { useContext, useMemo, useState } from 'react';

import {
  Braces,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  FileSearch,
  FileText,
} from 'lucide-react';

import { Markdown } from '@/core/components/chat/markdown';
import { JsonViewer } from '@/core/components/common/json-viewer';
import { cn } from '@/core/lib/cn';
import {
  type Citation,
  ExportContext,
  extractMessages,
  groupInput,
  INPUT_TEXT_KEYS,
  OUTPUT_TEXT_KEYS,
  type Payload,
  pickText,
  ROLE_BAR,
  ROLE_LABEL,
  type RoleMsg,
} from '@/system/call_logs/components/trace-parse';

/** 悬浮复制按钮：贴右上角，hover 显现，点后短暂打勾 */
const CopyBtn = ({ text }: { text: string }) => {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      title="复制"
      onClick={() => {
        void navigator.clipboard.writeText(text);
        setDone(true);
        setTimeout(() => setDone(false), 1200);
      }}
      className="absolute top-0.5 right-0.5 z-10 rounded p-1 text-stone-400 opacity-0 transition hover:bg-stone-100 hover:text-stone-700 group-hover/msg:opacity-100"
    >
      {done ? (
        <Check className="h-3.5 w-3.5 text-emerald-500" />
      ) : (
        <Copy className="h-3.5 w-3.5" />
      )}
    </button>
  );
};

/** 可折叠小节：标题 + chevron + 可选计数徽标 + 右侧附加 */
const Collapsible = ({
  label,
  count,
  defaultOpen = true,
  right,
  children,
}: {
  label: string;
  count?: number;
  defaultOpen?: boolean;
  right?: React.ReactNode;
  children: React.ReactNode;
}) => {
  const forced = useContext(ExportContext);
  const [open, setOpen] = useState(defaultOpen);
  const isOpen = forced || open;
  return (
    <div>
      <div className="flex h-6 items-center justify-between">
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          className="flex items-center gap-1 text-[11.5px] font-medium text-stone-600 hover:text-stone-900"
        >
          {isOpen ? (
            <ChevronDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
          {label}
          {count != null && (
            <span className="ml-0.5 rounded bg-stone-100 px-1.5 text-[10px] text-stone-500">
              {count}
            </span>
          )}
        </button>
        {isOpen && right}
      </div>
      {isOpen && (
        <div className="mt-1 ml-[6px] border-l border-stone-200/70 pl-3">
          {children}
        </div>
      )}
    </div>
  );
};

/** 单条消息：左色条 + 角色名 + Markdown + 复制 */
const MsgBlock = ({
  role,
  content,
  label,
  strong,
}: RoleMsg & { label?: string; strong?: boolean }) => (
  <div className="group/msg relative pl-3.5">
    <span
      className={cn(
        'absolute top-1 bottom-1 left-0 rounded',
        strong ? 'w-1' : 'w-[3px]',
        ROLE_BAR[role] ?? 'bg-stone-300',
      )}
    />
    <CopyBtn text={content} />
    <div className="mb-1 text-[10.5px] font-medium text-stone-400">
      {label ?? ROLE_LABEL[role] ?? role}
    </div>
    <div className="text-[13px] leading-relaxed break-words text-stone-800">
      <Markdown content={content} />
    </div>
  </div>
);

/** 召回模式 → 分数语义标签 */
const SCORE_LABEL: Record<string, string> = {
  vector: '相似度',
  keyword: 'BM25',
  hybrid: '相关度',
};

/** 文件引用卡：来源 + 定位 + 召回分数 + 内容 */
const CitationCard = ({
  source,
  ref: cref,
  content,
  mode,
  score,
  vector_score,
  bm25_score,
  rerank_score,
}: Citation) => {
  const breakdown = [
    vector_score != null ? `向量 ${vector_score.toFixed(3)}` : null,
    bm25_score != null ? `BM25 ${bm25_score.toFixed(3)}` : null,
    rerank_score != null ? `重排 ${rerank_score.toFixed(3)}` : null,
  ]
    .filter(Boolean)
    .join(' · ');
  return (
    <div className="group/msg relative rounded-md border border-amber-200/70 bg-amber-50/40 px-3 py-2">
      <CopyBtn text={content} />
      <div className="mb-1 flex items-center gap-1.5 pr-6 text-[10.5px] font-medium text-amber-700">
        <FileSearch className="h-3 w-3 shrink-0" />
        <span className="truncate">{source}</span>
        <span className="font-mono text-amber-500/80">#{cref}</span>
        {score != null && (
          <span
            className="ml-auto shrink-0 rounded bg-amber-100 px-1.5 py-0.5 font-mono text-[10px] text-amber-700"
            title={breakdown || undefined}
          >
            {SCORE_LABEL[mode ?? ''] ?? '相关度'} {score.toFixed(3)}
          </span>
        )}
      </div>
      <div className="text-[12.5px] leading-relaxed break-words text-stone-700">
        <Markdown content={content} />
      </div>
    </div>
  );
};

/** 系统消息：整段渲染（参考资料不再从字符串里硬拆，改由 retriever 节点结构化呈现） */
const SystemBlock = ({ content }: { content: string }) => (
  <Collapsible label="系统">
    <MsgBlock role="system" content={content} label="系统提示词" />
  </Collapsible>
);

/** 渲染模式切换（Markdown / 原始 JSON） */
const RawToggle = ({
  raw,
  setRaw,
}: {
  raw: boolean;
  setRaw: (v: boolean) => void;
}) => (
  <div className="flex items-center gap-0.5">
    <button
      type="button"
      title="结构化渲染"
      onClick={() => setRaw(false)}
      className={cn(
        'rounded p-1 transition',
        !raw ? 'bg-stone-100 text-stone-700' : 'text-stone-300 hover:text-stone-500',
      )}
    >
      <FileText className="h-3.5 w-3.5" />
    </button>
    <button
      type="button"
      title="原始 JSON"
      onClick={() => setRaw(true)}
      className={cn(
        'rounded p-1 transition',
        raw ? 'bg-stone-100 text-stone-700' : 'text-stone-300 hover:text-stone-500',
      )}
    >
      <Braces className="h-3.5 w-3.5" />
    </button>
  </div>
);

const SectionTitle = ({
  title,
  open,
  onToggle,
  right,
}: {
  title: string;
  open: boolean;
  onToggle: () => void;
  right?: React.ReactNode;
}) => (
  <div className="flex h-6 items-center justify-between">
    <button
      type="button"
      onClick={onToggle}
      className="flex items-center gap-1 text-[12px] font-medium text-stone-700 hover:text-stone-900"
    >
      {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
      {title}
    </button>
    {open && right}
  </div>
);

const EmptyBox = () => (
  <div className="rounded-md border border-dashed border-stone-200 px-3 py-4 text-center text-[11.5px] text-stone-400">
    无内容
  </div>
);

// ── Fields：LangSmith 式键值树（非 LLM 节点的结构化 payload）──────────

const isPlainObj = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === 'object' && !Array.isArray(v);

/** 基本类型值渲染（带颜色区分） */
const PrimitiveVal = ({ v }: { v: unknown }) => {
  if (v === null || v === undefined)
    return <span className="text-stone-400 italic">null</span>;
  if (typeof v === 'boolean')
    return <span className="text-violet-600">{String(v)}</span>;
  if (typeof v === 'number')
    return <span className="tnum text-blue-600">{v}</span>;
  return <span className="break-words whitespace-pre-wrap text-stone-700">{String(v)}</span>;
};

/** 单个字段行：基本类型内联；对象/数组可展开（默认收起，显示条目数） */
const FieldRow = ({ k, v }: { k: string; v: unknown }) => {
  const nested = isPlainObj(v) || Array.isArray(v);
  const forced = useContext(ExportContext);
  const [open, setOpen] = useState(false);
  const isOpen = forced || open;
  if (!nested) {
    return (
      <div className="flex items-start gap-2 py-0.5 leading-relaxed">
        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-stone-300" />
        <span className="shrink-0 font-medium text-stone-500">{k}</span>
        <span className="min-w-0 text-[12.5px]">
          <PrimitiveVal v={v} />
        </span>
      </div>
    );
  }
  const count = Array.isArray(v) ? v.length : Object.keys(v as object).length;
  const summary = Array.isArray(v) ? `[${count} 项]` : `{${count} 项}`;
  return (
    <div className="py-0.5">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1.5 leading-relaxed hover:text-stone-900"
      >
        {isOpen ? (
          <ChevronDown className="h-3 w-3 text-stone-400" />
        ) : (
          <ChevronRight className="h-3 w-3 text-stone-400" />
        )}
        <span className="font-medium text-stone-500">{k}</span>
        <span className="text-[11px] text-stone-400">{summary}</span>
      </button>
      {isOpen && (
        <div className="mt-0.5 ml-2.5 border-l border-stone-200 pl-3">
          {Array.isArray(v) ? (
            v.map((item, i) => <FieldRow key={i} k={String(i)} v={item} />)
          ) : (
            <FieldsRows value={v as Record<string, unknown>} />
          )}
        </div>
      )}
    </div>
  );
};

const FieldsRows = ({ value }: { value: Record<string, unknown> }) => (
  <>
    {Object.entries(value).map(([k, v]) => (
      <FieldRow key={k} k={k} v={v} />
    ))}
  </>
);

/** Fields 容器：键值树（无多余标题头；外层「输入/输出」已是标题） */
const FieldsTree = ({ value }: { value: Payload }) => {
  const obj = value && typeof value === 'object' ? value : {};
  return (
    <div className="group/msg relative rounded-md border border-stone-200/70 bg-stone-50/40 p-2.5 font-mono text-[12px]">
      <CopyBtn text={JSON.stringify(value ?? {}, null, 2)} />
      <FieldsRows value={obj as Record<string, unknown>} />
    </div>
  );
};

/** 输入：结构化 messages → 系统 / 历史对话 / 本轮输入 分组 */
export const InputView = ({ payload }: { payload: Payload }) => {
  const messages = useMemo(() => extractMessages(payload, INPUT_TEXT_KEYS), [payload]);
  const [raw, setRaw] = useState(false);
  const [open, setOpen] = useState(true);
  const empty = !payload || Object.keys(payload).length === 0;

  const grouped = useMemo(
    () => (messages ? groupInput(messages) : null),
    [messages],
  );

  return (
    <div className="space-y-1.5">
      <SectionTitle
        title="输入"
        open={open}
        onToggle={() => setOpen(o => !o)}
        right={!empty ? <RawToggle raw={raw} setRaw={setRaw} /> : undefined}
      />
      {open && (
        <div className="ml-[18px]">
          {empty ? (
            <EmptyBox />
          ) : raw ? (
            <JsonViewer value={(payload as object) ?? {}} />
          ) : !grouped ? (
            <FieldsTree value={payload} />
          ) : (
            <div className="space-y-3">
              {grouped.system.map((s, i) => (
                <SystemBlock key={`sys-${i}`} content={s.content} />
              ))}
              {grouped.history.length > 0 && (
                <Collapsible label="历史对话" count={grouped.history.length} defaultOpen={false}>
                  <div className="space-y-3">
                    {grouped.history.map((m, i) => (
                      <MsgBlock key={`his-${i}`} {...m} />
                    ))}
                  </div>
                </Collapsible>
              )}
              {grouped.current && (
                <div className="rounded-md bg-blue-50/50 py-2 pr-2">
                  <MsgBlock {...grouped.current} label="本轮输入" strong />
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

/** 输出：单条 assistant 文本（高亮竖条），可切原始 */
export const OutputView = ({ payload }: { payload: Payload }) => {
  const messages = useMemo(() => extractMessages(payload, OUTPUT_TEXT_KEYS), [payload]);
  const text = useMemo(() => pickText(payload, OUTPUT_TEXT_KEYS), [payload]);
  // retriever 节点结构化引用：{citations:[{source,ref,content}]}
  const citations = useMemo<Citation[] | null>(() => {
    const c =
      payload && typeof payload === 'object'
        ? (payload as Record<string, unknown>).citations
        : null;
    if (!Array.isArray(c)) return null;
    const num = (v: unknown): number | undefined =>
      typeof v === 'number' && Number.isFinite(v) ? v : undefined;
    return c
      .filter((x): x is Record<string, unknown> => !!x && typeof x === 'object')
      .map(x => ({
        source: String(x.source ?? ''),
        ref: String(x.ref ?? ''),
        content: String(x.content ?? ''),
        mode: x.mode != null ? String(x.mode) : undefined,
        score: num(x.score),
        vector_score: num(x.vector_score),
        bm25_score: num(x.bm25_score),
        rerank_score: num(x.rerank_score),
      }));
  }, [payload]);
  const [raw, setRaw] = useState(false);
  const [open, setOpen] = useState(true);
  const empty = !payload || Object.keys(payload).length === 0;

  return (
    <div className="space-y-1.5">
      <SectionTitle
        title="输出"
        open={open}
        onToggle={() => setOpen(o => !o)}
        right={!empty ? <RawToggle raw={raw} setRaw={setRaw} /> : undefined}
      />
      {open && (
        <div className="ml-[18px]">
          {empty ? (
            <EmptyBox />
          ) : raw ? (
            <JsonViewer value={(payload as object) ?? {}} />
          ) : citations ? (
            <div className="space-y-2">
              {citations.map((c, i) => (
                <CitationCard key={i} {...c} />
              ))}
            </div>
          ) : messages ? (
            <div className="space-y-3">
              {messages.map((m, i) => (
                <MsgBlock key={i} {...m} />
              ))}
            </div>
          ) : text ? (
            <div className="group/msg relative pl-3.5">
              <span className="absolute top-1 bottom-1 left-0 w-1 rounded bg-violet-400" />
              <CopyBtn text={text} />
              <div className="text-[13px] leading-relaxed break-words text-stone-800">
                <Markdown content={text} />
              </div>
            </div>
          ) : (
            <FieldsTree value={payload} />
          )}
        </div>
      )}
    </div>
  );
};
