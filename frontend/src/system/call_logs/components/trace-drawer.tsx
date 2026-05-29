/** TraceDrawer —— LangSmith 式 trace 详情：左侧 observation 树，右侧选中节点详情。
 *
 * 点树里任一节点 → 右侧面板拉该节点的 call_log 详情（元信息 + 输入 + 输出）。
 * 默认选中根 trace。无顶部 tab。
 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { flushSync } from 'react-dom';

import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsDownUp,
  ChevronsRight,
  ChevronsUpDown,
  ChevronUp,
  Copy,
  Download,
  FileDown,
  Image as ImageIcon,
  Maximize,
  Minimize,
  RotateCw,
} from 'lucide-react';

import { StatBar, StatItem } from '@/core/components/common/stat-bar';
import { Badge } from '@/core/components/ui/badge';
import { Popover, PopoverContent, PopoverTrigger } from '@/core/components/ui/popover';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/core/components/ui/sheet';
import { cn } from '@/core/lib/cn';
import { formatCost, formatDateTime, formatDurationMs, formatTokens } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import { ObservationIconRail, ObservationTree } from '@/system/call_logs/components/observation-tree';
import {
  buildTraceText,
  downloadText,
  exportImage,
} from '@/system/call_logs/components/trace-export';
import { ExportContext } from '@/system/call_logs/components/trace-parse';
import { InputView, OutputView } from '@/system/call_logs/components/trace-payload';
import { callLogApi } from '@/system/call_logs/services/call-log';
import type {
  CallLogDetail,
  CallLogItem,
  TraceTreeNode,
} from '@/system/call_logs/types/call-log';

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
  const [widthPx, setWidthPx] = useState(1180);
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
  // 链路树列宽（右边缘可拖拽，和 drawer 左边缘一样的体验）
  const [treeWidth, setTreeWidth] = useState(440);
  const [treeResizing, setTreeResizing] = useState(false);

  const startTreeResize = (e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = treeWidth;
    const onMove = (ev: MouseEvent) => {
      setTreeWidth(Math.max(240, Math.min(720, startW + ev.clientX - startX)));
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
      setTreeResizing(false);
    };
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
    setTreeResizing(true);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

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
        <div
          style={{ width: treeWidth }}
          className="shrink-0 overflow-y-auto border-r border-stone-200/70 p-3"
        >
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

      {/* 树列右边缘拖拽手柄（树展开时才有） */}
      {!treeHidden && (
        <div
          onMouseDown={startTreeResize}
          title="拖拽调整链路树宽度"
          className={cn(
            '-ml-px w-1.5 shrink-0 cursor-col-resize transition-colors',
            treeResizing ? 'bg-blue-300/60' : 'hover:bg-blue-300/60',
          )}
        />
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

/** 导出菜单项 */
const ExportItem = ({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) => (
  <button
    type="button"
    onClick={onClick}
    className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12px] text-stone-600 transition hover:bg-stone-100 hover:text-stone-900"
  >
    <span className="text-stone-400">{icon}</span>
    {label}
  </button>
);

/** 右侧节点详情：元信息 + 输入 + 输出 + 一键导出（文字 / 图片，带元信息） */
const NodeDetail = ({ node }: { node: CallLogDetail }) => {
  const detailRef = useRef<HTMLDivElement>(null);
  // 导出图片时：强制展开所有折叠 + 隐藏导出按钮（截图全量、无多余控件）
  const [exporting, setExporting] = useState(false);
  const nodeName = node.request_id.includes('.')
    ? node.request_id.slice(node.request_id.indexOf('.') + 1)
    : node.agent_key;
  const shortId = node.request_id.slice(0, 12);

  const copyText = () => {
    void navigator.clipboard.writeText(buildTraceText(node));
    toast.success('已复制溯源文本');
  };
  const dlText = () => downloadText(`trace-${shortId}.md`, buildTraceText(node));
  const dlImage = async () => {
    if (!detailRef.current) return;
    // flushSync 同步触发「全展开 + 隐藏按钮」的重渲染，再截图，最后还原
    flushSync(() => setExporting(true));
    try {
      await exportImage(detailRef.current, `trace-${shortId}.png`);
    } catch {
      toast.error('导出图片失败');
    } finally {
      setExporting(false);
    }
  };

  return (
    <ExportContext.Provider value={exporting}>
      <div ref={detailRef} className="space-y-4 bg-[var(--color-paper)]">
        {/* 标题行 + 导出 */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="rounded bg-violet-50 px-1.5 py-0.5 font-mono text-[11px] text-violet-600">
                {node.observation_type}
              </span>
              <span className="text-[14px] font-semibold text-stone-900">{nodeName}</span>
            </div>
            {/* nowrap + margin（不用 flex-wrap/gap）：html-to-image 对 flex-wrap+gap 会误判
                提前换行，导致导出图里「请求」另起一行；改用 whitespace-nowrap 锁单行 */}
            <div className="mt-1.5 flex items-center text-[11.5px]">
              <span className="mr-4 whitespace-nowrap">
                <span className="text-stone-400">开始</span>{' '}
                <span className="font-mono text-stone-600">{formatDateTime(node.created_at)}</span>
              </span>
              {node.session_id && (
                <span className="mr-4 whitespace-nowrap">
                  <span className="text-stone-400">会话</span>{' '}
                  <span className="font-mono text-stone-600">{node.session_id}</span>
                </span>
              )}
              <span className="whitespace-nowrap">
                <span className="text-stone-400">请求</span>{' '}
                <button
                  type="button"
                  title={`点击复制 ${node.request_id}`}
                  onClick={() => void navigator.clipboard.writeText(node.request_id)}
                  className="font-mono text-stone-600 hover:text-blue-600"
                >
                  {node.request_id.length > 16
                    ? `${node.request_id.slice(0, 16)}…`
                    : node.request_id}
                </button>
              </span>
            </div>
          </div>
          {!exporting && (
            <Popover>
              <PopoverTrigger asChild>
                <button
                  type="button"
                  title="导出 trace"
                  className="inline-flex shrink-0 items-center gap-1 rounded-md border border-stone-200 px-2 py-1 text-[11.5px] text-stone-600 transition hover:border-stone-300 hover:text-stone-900"
                >
                  <Download className="h-3.5 w-3.5" />
                  导出
                </button>
              </PopoverTrigger>
              <PopoverContent align="end" className="!w-44 !p-1">
                <ExportItem
                  icon={<Copy className="h-3.5 w-3.5" />}
                  label="复制文字"
                  onClick={copyText}
                />
                <ExportItem
                  icon={<FileDown className="h-3.5 w-3.5" />}
                  label="下载文字 .md"
                  onClick={dlText}
                />
                <ExportItem
                  icon={<ImageIcon className="h-3.5 w-3.5" />}
                  label="下载图片 .png"
                  onClick={() => void dlImage()}
                />
              </PopoverContent>
            </Popover>
          )}
        </div>

      {/* stat bar：指标平铺，无填充无卡格；极淡竖发丝分隔 + 放大数值出层次 */}
      <StatBar>
        <StatItem k="状态" v={node.success ? '成功' : `失败 ${node.code}`} tone={node.success ? 'ok' : 'err'} />
        <StatItem k="耗时" v={formatDurationMs(node.duration_ms)} />
        <StatItem k="模型" v={node.model_code || '—'} mono />
        <StatItem
          k="Token"
          v={node.total_tokens != null ? formatTokens(node.total_tokens) : '—'}
          sub={node.total_tokens != null ? `↑${node.prompt_tokens ?? 0} ↓${node.completion_tokens ?? 0}` : undefined}
        />
        <StatItem k="成本" v={node.cost_usd != null ? formatCost(node.cost_usd) : '—'} />
        <StatItem k="渠道" v={node.channel || '—'} />
      </StatBar>

      {node.error_message && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] text-rose-700">
          {node.error_message}
        </div>
      )}

        <InputView payload={node.request_payload} />
        <OutputView payload={node.response_payload} />
      </div>
    </ExportContext.Provider>
  );
};

