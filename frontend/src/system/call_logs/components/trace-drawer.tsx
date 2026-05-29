/** TraceDrawer —— LangSmith 式 trace 详情：左侧 observation 树，右侧选中节点详情。
 *
 * 点树里任一节点 → 右侧面板拉该节点的 call_log 详情（元信息 + 输入 + 输出）。
 * 默认选中根 trace。无顶部 tab。
 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import {
  Braces,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsDownUp,
  ChevronsRight,
  ChevronsUpDown,
  ChevronUp,
  FileText,
  Maximize,
  Minimize,
  RotateCw,
} from 'lucide-react';

import { Markdown } from '@/core/components/chat/markdown';
import { JsonViewer } from '@/core/components/common/json-viewer';
import { Badge } from '@/core/components/ui/badge';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/core/components/ui/sheet';
import { cn } from '@/core/lib/cn';
import { formatCost, formatDateTime, formatDurationMs, formatTokens } from '@/core/lib/format';
import { ObservationIconRail, ObservationTree } from '@/system/call_logs/components/observation-tree';
import { callLogApi } from '@/system/call_logs/services/call-log';
import type { CallLogItem, TraceTreeNode } from '@/system/call_logs/types/call-log';

interface Props {
  callLog: CallLogItem | null;
  onClose: () => void;
  /** 上/下一条（列表上下文）；不传则隐藏对应按钮 */
  onPrev?: () => void;
  onNext?: () => void;
  hasPrev?: boolean;
  hasNext?: boolean;
}

export const TraceDrawer = ({ callLog, onClose, onPrev, onNext, hasPrev, hasNext }: Props) => {
  const qc = useQueryClient();
  const [full, setFull] = useState(false);
  const [widthPx, setWidthPx] = useState(1100);
  const [resizing, setResizing] = useState(false);

  const refresh = () => {
    if (!callLog) return;
    qc.invalidateQueries({ queryKey: ['call-log-tree', callLog.request_id] });
    qc.invalidateQueries({ queryKey: ['call-log-detail'] });
  };

  // 左边缘拖拽调宽：面板右贴边，宽度 = 视口宽 - 鼠标 x，clamp [560, 视口-80]
  const startResize = (e: React.MouseEvent) => {
    e.preventDefault();
    const onMove = (ev: MouseEvent) => {
      const w = Math.max(560, Math.min(window.innerWidth - 80, window.innerWidth - ev.clientX));
      setWidthPx(w);
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      // 全局锁的光标/选区还原（拖拽时面板边缘会离开鼠标，靠全局锁避免光标闪烁）
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
      setResizing(false);
    };
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
    setResizing(true);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  return (
    <Sheet open={callLog != null} onOpenChange={o => !o && onClose()}>
      <SheetContent
        width={full ? 'w-screen' : ''}
        style={full ? undefined : { width: widthPx }}
      >
        {/* 左边缘拖拽手柄（全屏时禁用） */}
        {!full && (
          <div
            onMouseDown={startResize}
            title="拖拽调整宽度"
            className={cn(
              'absolute top-0 bottom-0 left-0 z-20 w-1.5 cursor-col-resize transition-colors',
              resizing ? 'bg-blue-300/60' : 'hover:bg-blue-300/60',
            )}
          />
        )}
        <SheetHeader className="!px-4 !py-2.5">
          <div className="flex items-center gap-2">
            {/* LangSmith 式功能 icon 栏：收起 / 全屏 / 上一条 / 下一条 / 刷新 */}
            <div className="flex items-center gap-0.5">
              <IconBtn title="收起" onClick={onClose}>
                <ChevronsRight className="h-[15px] w-[15px]" />
              </IconBtn>
              <IconBtn title={full ? '退出全屏' : '全屏'} onClick={() => setFull(f => !f)}>
                {full ? (
                  <Minimize className="h-[15px] w-[15px]" />
                ) : (
                  <Maximize className="h-[15px] w-[15px]" />
                )}
              </IconBtn>
              <span className="mx-0.5 h-4 w-px bg-stone-200" />
              <IconBtn title="上一条" onClick={onPrev} disabled={!onPrev || !hasPrev}>
                <ChevronUp className="h-[15px] w-[15px]" />
              </IconBtn>
              <IconBtn title="下一条" onClick={onNext} disabled={!onNext || !hasNext}>
                <ChevronDown className="h-[15px] w-[15px]" />
              </IconBtn>
              <IconBtn title="刷新" onClick={refresh}>
                <RotateCw className="h-[15px] w-[15px]" />
              </IconBtn>
            </div>
            <span className="h-4 w-px bg-stone-200" />
            <SheetTitle className="!m-0">
              {callLog ? (
                <div className="flex items-center gap-2">
                  <span>{callLog.agent_key}</span>
                  <span className="truncate font-mono text-[11.5px] text-stone-500">
                    {callLog.request_id}
                  </span>
                  <Badge
                    variant="outline"
                    className={cn(
                      'text-[10.5px]',
                      callLog.success
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-rose-50 text-rose-700',
                    )}
                  >
                    {callLog.success ? '成功' : `失败 ${callLog.code}`}
                  </Badge>
                  <span className="tnum font-mono text-[11.5px] text-stone-500">
                    {formatDurationMs(callLog.duration_ms)}
                  </span>
                </div>
              ) : (
                '加载中…'
              )}
            </SheetTitle>
          </div>
        </SheetHeader>
        <SheetBody className="!p-0">
          {/* 按 request_id remount → 切到新 trace 时选中态自动重置回根（避开 effect setState） */}
          {callLog && <TraceBody key={callLog.request_id} requestId={callLog.request_id} />}
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
};

const IconBtn = ({
  title,
  onClick,
  disabled,
  children,
}: {
  title: string;
  onClick?: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) => (
  <button
    type="button"
    title={title}
    onClick={onClick}
    disabled={disabled}
    className={cn(
      'rounded-md p-1.5 text-stone-500 transition',
      disabled ? 'cursor-not-allowed opacity-30' : 'hover:bg-stone-100 hover:text-stone-800',
    )}
  >
    {children}
  </button>
);

const TraceBody = ({ requestId }: { requestId: string }) => {
  // 选中节点 id（call_log id）；null → 派生为根，不用 effect 同步
  const [picked, setPicked] = useState<string | null>(null);
  // 折叠/展开全树：切换时 remount ObservationTree 让每行按此初始化，避开 effect
  const [treeCollapsed, setTreeCollapsed] = useState(false);
  // 收起整列链路树（详情铺满）
  const [treeHidden, setTreeHidden] = useState(false);

  const treeQ = useQuery({
    queryKey: ['call-log-tree', requestId],
    queryFn: () => callLogApi.tree(requestId),
  });

  const effectiveId = picked ?? (treeQ.data ? String(treeQ.data.id) : null);

  const detailQ = useQuery({
    queryKey: ['call-log-detail', effectiveId],
    queryFn: () => callLogApi.get(effectiveId!),
    enabled: effectiveId != null,
  });

  return (
    <div className="flex h-full min-h-0">
      {/* 左：observation 树（可整列收起） */}
      {treeHidden ? (
        <div className="flex w-11 shrink-0 flex-col items-center gap-1 overflow-y-auto border-r border-stone-200/70 py-3">
          <button
            type="button"
            title="展开链路树"
            onClick={() => setTreeHidden(false)}
            className="rounded p-1 text-stone-400 transition hover:bg-stone-100 hover:text-stone-700"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
          {treeQ.data && (
            <ObservationIconRail
              root={treeQ.data}
              selectedId={effectiveId ?? undefined}
              onSelect={(n: TraceTreeNode) => setPicked(String(n.id))}
            />
          )}
        </div>
      ) : (
        <div className="w-[440px] shrink-0 overflow-y-auto border-r border-stone-200/70 p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[11px] font-medium text-stone-500">调用链路</span>
            <div className="flex items-center gap-0.5">
              <button
                type="button"
                title={treeCollapsed ? '展开全部节点' : '折叠全部节点'}
                onClick={() => setTreeCollapsed(c => !c)}
                className="rounded p-1 text-stone-400 transition hover:bg-stone-100 hover:text-stone-700"
              >
                {treeCollapsed ? (
                  <ChevronsUpDown className="h-3.5 w-3.5" />
                ) : (
                  <ChevronsDownUp className="h-3.5 w-3.5" />
                )}
              </button>
              <button
                type="button"
                title="收起链路树"
                onClick={() => setTreeHidden(true)}
                className="rounded p-1 text-stone-400 transition hover:bg-stone-100 hover:text-stone-700"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
          {treeQ.isLoading ? (
            <div className="py-10 text-center text-sm text-stone-400">加载链路…</div>
          ) : treeQ.data ? (
            <ObservationTree
              key={treeCollapsed ? 'collapsed' : 'expanded'}
              root={treeQ.data}
              selectedId={effectiveId}
              defaultCollapsed={treeCollapsed}
              onSelect={(n: TraceTreeNode) => setPicked(String(n.id))}
            />
          ) : (
            <div className="py-10 text-center text-sm text-stone-400">无法加载链路</div>
          )}
        </div>
      )}

      {/* 右：选中节点详情 */}
      <div className="min-w-0 flex-1 overflow-y-auto p-4">
        {detailQ.isLoading || !detailQ.data ? (
          <div className="py-10 text-center text-sm text-stone-400">加载详情…</div>
        ) : (
          // 按节点 remount：让 PayloadView 的 raw/open state 随节点重新初始化，
          // 否则先看无文本节点(raw=true) 再切到有文本节点会卡在原始 JSON
          <NodeDetail key={String(detailQ.data.id)} node={detailQ.data} />
        )}
      </div>
    </div>
  );
};

type Payload = Record<string, unknown> | null | undefined;

/** 从 payload 里抽「主文本」（prompt/output/answer 等），用于 Markdown 渲染 */
const INPUT_TEXT_KEYS = ['prompt_preview', 'input', 'question', 'query', 'text', 'content'];
const OUTPUT_TEXT_KEYS = ['output_preview', 'output', 'answer', 'text', 'content'];

const pickText = (payload: Payload, keys: string[]): string | null => {
  if (!payload || typeof payload !== 'object') return null;
  for (const k of keys) {
    const v = (payload as Record<string, unknown>)[k];
    if (typeof v === 'string' && v.trim()) return v;
  }
  return null;
};

// prompt 快照格式 "[role] content"（角色间以 \n 分隔，content 内部也可能含 \n）。
// 按已知角色标记切成消息块，逐块按角色渲染。
const ROLE_RE = /(?=^\[(?:system|human|ai|user|assistant|tool|function)\][ \t]?)/im;
const ROLE_LABEL: Record<string, string> = {
  system: '系统',
  human: '用户',
  user: '用户',
  ai: '助手',
  assistant: '助手',
  tool: '工具',
  function: '工具',
};
const ROLE_BAR: Record<string, string> = {
  system: 'bg-stone-400',
  human: 'bg-blue-500',
  user: 'bg-blue-500',
  ai: 'bg-violet-400',
  assistant: 'bg-violet-400',
  tool: 'bg-amber-400',
  function: 'bg-amber-400',
};

interface RoleMsg {
  role: string;
  content: string;
}

/** 解析 "[role] ..." 多消息文本；非该格式返 null */
const parseMessages = (text: string): RoleMsg[] | null => {
  if (!/^\[(system|human|ai|user|assistant|tool|function)\]/i.test(text.trimStart())) return null;
  const parts = text.split(ROLE_RE).filter(p => p.trim());
  const msgs: RoleMsg[] = [];
  for (const p of parts) {
    const m = p.match(/^\[(\w+)\][ \t]?([\s\S]*)$/);
    if (m) msgs.push({ role: m[1].toLowerCase(), content: m[2].trim() });
  }
  return msgs.length ? msgs : null;
};

/** 右侧节点详情：元信息 + 输入 + 输出（Markdown / 原始 可切） */
const NodeDetail = ({
  node,
}: {
  node: CallLogItem & { request_payload?: Payload; response_payload?: Payload };
}) => {
  const nodeName = node.request_id.includes('.')
    ? node.request_id.slice(node.request_id.indexOf('.') + 1)
    : node.agent_key;
  return (
    <div className="space-y-4">
      {/* 标题 + 身份 mono 行（开始时间 / 请求 / 会话 置顶并排） */}
      <div>
        <div className="flex items-center gap-2">
          <span className="rounded bg-violet-50 px-1.5 py-0.5 font-mono text-[11px] text-violet-600">
            {node.observation_type}
          </span>
          <span className="text-[14px] font-semibold text-stone-900">{nodeName}</span>
        </div>
        <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[11.5px]">
          <span>
            <span className="text-stone-400">开始</span>{' '}
            <span className="font-mono text-stone-600">{formatDateTime(node.created_at)}</span>
          </span>
          <span className="min-w-0">
            <span className="text-stone-400">请求</span>{' '}
            <button
              type="button"
              title="点击复制"
              onClick={() => void navigator.clipboard.writeText(node.request_id)}
              className="font-mono text-stone-600 hover:text-blue-600"
            >
              {node.request_id}
            </button>
          </span>
          {node.session_id && (
            <span>
              <span className="text-stone-400">会话</span>{' '}
              <span className="font-mono text-stone-600">{node.session_id}</span>
            </span>
          )}
        </div>
      </div>

      {/* stat bar：指标平铺，淡色圆角带承托，无分隔线（去线条感） */}
      <div className="flex flex-wrap gap-x-7 gap-y-3 rounded-lg bg-stone-50 px-4 py-3">
        <Stat k="状态" v={node.success ? '成功' : `失败 ${node.code}`} tone={node.success ? 'ok' : 'err'} />
        <Stat k="耗时" v={formatDurationMs(node.duration_ms)} />
        <Stat k="模型" v={node.model_code || '—'} mono />
        <Stat
          k="Token"
          v={node.total_tokens != null ? formatTokens(node.total_tokens) : '—'}
          sub={node.total_tokens != null ? `↑${node.prompt_tokens ?? 0} ↓${node.completion_tokens ?? 0}` : undefined}
        />
        <Stat k="成本" v={node.cost_usd != null ? formatCost(node.cost_usd) : '—'} />
        <Stat k="渠道" v={node.channel || '—'} />
      </div>

      {node.error_message && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] text-rose-700">
          {node.error_message}
        </div>
      )}

      <PayloadView title="输入" payload={node.request_payload} textKeys={INPUT_TEXT_KEYS} />
      <PayloadView title="输出" payload={node.response_payload} textKeys={OUTPUT_TEXT_KEYS} />
    </div>
  );
};

/** stat bar 单项：label 小灰 + value 粗，右侧竖线分隔 */
const Stat = ({
  k,
  v,
  sub,
  mono,
  tone,
}: {
  k: string;
  v: string;
  sub?: string;
  mono?: boolean;
  tone?: 'ok' | 'err';
}) => (
  <div>
    <div className="text-[10.5px] text-stone-400">{k}</div>
    <div className="mt-0.5 flex items-baseline gap-1.5">
      <span
        className={cn(
          'tnum text-[13.5px] font-semibold',
          tone === 'ok' ? 'text-emerald-600' : tone === 'err' ? 'text-rose-600' : 'text-stone-800',
          mono && 'font-mono text-[12.5px]',
        )}
      >
        {v}
      </span>
      {sub && <span className="tnum text-[11px] font-normal text-stone-400">{sub}</span>}
    </div>
  </div>
);

/** 输入/输出：有「主文本」时默认 Markdown 渲染（保留换行），可切原始 JSON */
const PayloadView = ({
  title,
  payload,
  textKeys,
}: {
  title: string;
  payload: Payload;
  textKeys: string[];
}) => {
  const text = pickText(payload, textKeys);
  const messages = text ? parseMessages(text) : null;
  const [raw, setRaw] = useState(!text); // 无主文本时直接看原始
  const [open, setOpen] = useState(true); // 默认展开，可折叠
  const empty = !payload || Object.keys(payload).length === 0;

  return (
    <div className="space-y-1.5">
      {/* 固定行高 h-6：折叠时右侧切换消失也不让标题上下跳动 */}
      <div className="flex h-6 items-center justify-between">
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          className="flex items-center gap-1 text-[12px] font-medium text-stone-700 hover:text-stone-900"
        >
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          {title}
        </button>
        {open && text && (
          <div className="flex items-center gap-0.5">
            <button
              type="button"
              title="Markdown 渲染"
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
        )}
      </div>
      {!open ? null : empty ? (
        <div className="rounded-md border border-dashed border-stone-200 px-3 py-4 text-center text-[11.5px] text-stone-400">
          无内容
        </div>
      ) : !raw && messages ? (
        <div className="max-h-[460px] space-y-3 overflow-y-auto rounded-lg bg-stone-50 px-3.5 py-3">
          {messages.map((m, i) => (
            <div key={i} className="relative pl-3.5">
              {/* 轻量左色条替代描边卡片：系统=灰 / 用户=蓝 / 助手=紫 / 工具=琥珀 */}
              <span className={cn('absolute top-1 bottom-1 left-0 w-[3px] rounded', ROLE_BAR[m.role] ?? 'bg-stone-300')} />
              <div className="mb-1 text-[10.5px] font-medium text-stone-400">
                {ROLE_LABEL[m.role] ?? m.role}
              </div>
              <div className="text-[13px] leading-relaxed text-stone-800">
                <Markdown content={m.content} />
              </div>
            </div>
          ))}
        </div>
      ) : !raw && text ? (
        <div className="max-h-[420px] overflow-y-auto rounded-lg bg-stone-50 px-3.5 py-3 text-[13px] leading-relaxed text-stone-800">
          <Markdown content={text} />
        </div>
      ) : (
        <JsonViewer value={(payload as object) ?? {}} />
      )}
    </div>
  );
};

