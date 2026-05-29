/** TraceDrawer —— LangSmith 式 trace 详情：左侧 observation 树，右侧选中节点详情。
 *
 * 点树里任一节点 → 右侧面板拉该节点的 call_log 详情（元信息 + 输入 + 输出）。
 * 默认选中根 trace。无顶部 tab。
 */

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

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
import { ObservationTree } from '@/system/call_logs/components/observation-tree';
import { callLogApi } from '@/system/call_logs/services/call-log';
import type { CallLogItem, TraceTreeNode } from '@/system/call_logs/types/call-log';

interface Props {
  callLog: CallLogItem | null;
  onClose: () => void;
}

export const TraceDrawer = ({ callLog, onClose }: Props) => (
  <Sheet open={callLog != null} onOpenChange={o => !o && onClose()}>
    <SheetContent width="w-[1100px]">
      <SheetHeader>
        <SheetTitle>
          {callLog ? (
            <div className="flex items-center gap-2">
              <span>{callLog.agent_key}</span>
              <span className="font-mono text-[11.5px] text-stone-500">
                {callLog.request_id.slice(0, 16)}…
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
      </SheetHeader>
      <SheetBody className="!p-0">
        {/* 按 request_id remount → 切到新 trace 时选中态自动重置回根（避开 effect setState） */}
        {callLog && <TraceBody key={callLog.request_id} requestId={callLog.request_id} />}
      </SheetBody>
    </SheetContent>
  </Sheet>
);

const TraceBody = ({ requestId }: { requestId: string }) => {
  // 选中节点 id（call_log id）；null → 派生为根，不用 effect 同步
  const [picked, setPicked] = useState<string | null>(null);

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
      {/* 左：observation 树 */}
      <div className="w-[440px] shrink-0 overflow-y-auto border-r border-stone-200/70 p-3">
        <div className="mb-2 text-[11px] text-stone-500">调用链路 · 点节点看右侧详情</div>
        {treeQ.isLoading ? (
          <div className="py-10 text-center text-sm text-stone-400">加载链路…</div>
        ) : treeQ.data ? (
          <ObservationTree
            root={treeQ.data}
            selectedId={effectiveId}
            onSelect={(n: TraceTreeNode) => setPicked(String(n.id))}
          />
        ) : (
          <div className="py-10 text-center text-sm text-stone-400">无法加载链路</div>
        )}
      </div>

      {/* 右：选中节点详情 */}
      <div className="min-w-0 flex-1 overflow-y-auto p-4">
        {detailQ.isLoading || !detailQ.data ? (
          <div className="py-10 text-center text-sm text-stone-400">加载详情…</div>
        ) : (
          <NodeDetail node={detailQ.data} />
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
      <div className="flex items-center gap-2">
        <span className="rounded bg-stone-100 px-1.5 py-0.5 font-mono text-[11px] text-stone-600">
          {node.observation_type}
        </span>
        <span className="text-[13px] font-medium text-stone-900">{nodeName}</span>
      </div>

      {/* 元信息卡片 */}
      <div className="grid grid-cols-2 gap-2">
        <Meta label="状态" value={node.success ? '成功' : `失败 ${node.code}`} tone={node.success ? 'ok' : 'err'} />
        <Meta label="耗时" value={formatDurationMs(node.duration_ms)} />
        <Meta label="模型" value={node.model_code || '—'} mono />
        <Meta
          label="Token"
          value={
            node.total_tokens != null
              ? `${formatTokens(node.total_tokens)} (↑${node.prompt_tokens ?? 0} ↓${node.completion_tokens ?? 0})`
              : '—'
          }
        />
        <Meta label="成本" value={node.cost_usd != null ? formatCost(node.cost_usd) : '—'} />
        <Meta label="渠道" value={node.channel || '—'} />
        <Meta label="开始时间" value={formatDateTime(node.created_at)} mono />
        <Meta label="请求 ID" value={node.request_id} mono copyable />
      </div>

      {node.error_message && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] text-rose-700">
          {node.error_message}
        </div>
      )}

      <PayloadView title="输入" payload={node.request_payload} textKeys={INPUT_TEXT_KEYS} />
      <PayloadView title="输出" payload={node.response_payload} textKeys={OUTPUT_TEXT_KEYS} />

      <div className="border-t border-stone-200 pt-2 text-[11px] text-stone-500">
        会话 <span className="font-mono">{node.session_id ?? '—'}</span>
      </div>
    </div>
  );
};

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
  const [raw, setRaw] = useState(!text); // 无主文本时直接看原始
  const empty = !payload || Object.keys(payload).length === 0;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[12px] font-medium text-stone-700">{title}</span>
        {text && (
          <div className="flex overflow-hidden rounded-md border border-stone-200 text-[11px]">
            <button
              type="button"
              onClick={() => setRaw(false)}
              className={cn('px-2 py-0.5', !raw ? 'bg-stone-800 text-white' : 'text-stone-500 hover:bg-stone-100')}
            >
              Markdown
            </button>
            <button
              type="button"
              onClick={() => setRaw(true)}
              className={cn('px-2 py-0.5', raw ? 'bg-stone-800 text-white' : 'text-stone-500 hover:bg-stone-100')}
            >
              原始
            </button>
          </div>
        )}
      </div>
      {empty ? (
        <div className="rounded-md border border-dashed border-stone-200 px-3 py-4 text-center text-[11.5px] text-stone-400">
          无内容
        </div>
      ) : !raw && text ? (
        <div className="max-h-[420px] overflow-y-auto rounded-md border border-stone-200/70 bg-white px-3 py-2 text-[13px] leading-relaxed">
          <Markdown content={text} />
        </div>
      ) : (
        <JsonViewer value={(payload as object) ?? {}} />
      )}
    </div>
  );
};

const Meta = ({
  label,
  value,
  mono,
  tone,
  copyable,
}: {
  label: string;
  value: string;
  mono?: boolean;
  tone?: 'ok' | 'err';
  copyable?: boolean;
}) => (
  <div className="rounded-md border border-stone-200/70 bg-white px-2.5 py-1.5">
    <div className="text-[10.5px] text-stone-500">{label}</div>
    <div
      className={cn(
        'mt-0.5 truncate text-[12px]',
        mono && 'font-mono',
        tone === 'ok' ? 'text-emerald-700' : tone === 'err' ? 'text-rose-600' : 'text-stone-800',
        copyable && 'cursor-pointer hover:text-blue-600',
      )}
      title={copyable ? '点击复制' : value}
      onClick={copyable ? () => void navigator.clipboard.writeText(value) : undefined}
    >
      {value}
    </div>
  </div>
);
