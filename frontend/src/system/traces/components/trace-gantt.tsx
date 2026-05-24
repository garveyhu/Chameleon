/** Trace 甘特时间轴
 *
 * - 竖向虚拟滚动（@tanstack/react-virtual）撑 1000+ spans 不卡
 * - 横向缩放（ganttZoom）：label 列 sticky-left 固定，时间区可横向滚动，ruler 同步
 * - 选中 / hover / 折叠 全走 trace store，与左侧观测树联动
 * - bar 上叠 cost-label（成本或 token）
 */

import { useVirtualizer } from '@tanstack/react-virtual';
import { ChevronDown, ChevronRight, Minus, Plus } from 'lucide-react';
import { useMemo, useRef, useState } from 'react';

import { useElementWidth } from '@/core/hooks/use-element-width';
import { cn } from '@/core/lib/cn';
import { formatDurationMs } from '@/core/lib/format';
import { useTraceStore } from '@/core/stores/trace';
import type { TraceTreeNode } from '@/system/call_logs/types/call-log';
import { GanttBar } from '@/system/traces/components/gantt-bar';
import {
  computeBounds,
  flattenTrace,
  timeTicks,
} from '@/system/traces/utils/gantt-model';

const LABEL_W = 210;
const ROW_H = 30;
const RULER_H = 24;

interface Props {
  root: TraceTreeNode;
  /** 选中节点回调（与 NodeDetail 联动；可省，store 已记 selectedId） */
  onSelect?: (node: TraceTreeNode) => void;
}

export const TraceGantt = ({ root, onSelect }: Props) => {
  const selectedId = useTraceStore(s => s.selectedId);
  const hoveredId = useTraceStore(s => s.hoveredId);
  const collapsed = useTraceStore(s => s.collapsed);
  const zoom = useTraceStore(s => s.ganttZoom);
  const select = useTraceStore(s => s.select);
  const hover = useTraceStore(s => s.hover);
  const toggleCollapse = useTraceStore(s => s.toggleCollapse);
  const setGanttZoom = useTraceStore(s => s.setGanttZoom);

  const scrollRef = useRef<HTMLDivElement>(null);
  const containerW = useElementWidth(scrollRef);
  const [scrollLeft, setScrollLeft] = useState(0);

  const bounds = useMemo(() => computeBounds(root), [root]);
  const rows = useMemo(
    () => flattenTrace(root, collapsed),
    [root, collapsed],
  );

  const timelineW = Math.max(0, containerW - LABEL_W) * zoom;
  const contentW = LABEL_W + timelineW;
  const ticks = useMemo(() => timeTicks(bounds.totalMs, 5), [bounds.totalMs]);

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_H,
    overscan: 15,
  });

  return (
    <div className="flex flex-col">
      {/* 缩放工具条 */}
      <div className="mb-1 flex items-center justify-end gap-1 text-stone-500">
        <button
          type="button"
          title="缩小"
          className="rounded p-0.5 hover:bg-stone-100 hover:text-stone-800"
          onClick={() => setGanttZoom(zoom / 1.5)}
        >
          <Minus className="h-3.5 w-3.5" />
        </button>
        <span className="w-10 text-center font-mono text-[10.5px] tabular-nums">
          {Math.round(zoom * 100)}%
        </span>
        <button
          type="button"
          title="放大"
          className="rounded p-0.5 hover:bg-stone-100 hover:text-stone-800"
          onClick={() => setGanttZoom(zoom * 1.5)}
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* ruler：label 占位静止，时间刻度随 body 横向滚动 */}
      <div className="flex" style={{ height: RULER_H }}>
        <div
          className="shrink-0 text-[10.5px] text-stone-400"
          style={{ width: LABEL_W }}
        >
          时间轴
        </div>
        <div className="relative flex-1 overflow-hidden border-b border-stone-200/70">
          <div
            className="relative h-full"
            style={{ width: timelineW, transform: `translateX(${-scrollLeft}px)` }}
          >
            {ticks.map((ms, i) => (
              <span
                key={i}
                className="absolute top-0 font-mono text-[9.5px] text-stone-400"
                style={{
                  left: `${(ms / bounds.totalMs) * 100}%`,
                  transform: i === ticks.length - 1 ? 'translateX(-100%)' : undefined,
                }}
              >
                {formatDurationMs(ms)}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* body：唯一滚动容器（竖向虚拟 + 横向缩放） */}
      <div
        ref={scrollRef}
        className="overflow-auto"
        style={{ height: Math.min(520, Math.max(180, rows.length * ROW_H + 8)) }}
        onScroll={e => setScrollLeft(e.currentTarget.scrollLeft)}
      >
        <div
          className="relative"
          style={{ width: contentW, height: virtualizer.getTotalSize() }}
        >
          {virtualizer.getVirtualItems().map(vi => {
            const { node, depth, hasChildren, collapsed: isCol } = rows[vi.index];
            const isSel = node.request_id === selectedId;
            const isHov = node.request_id === hoveredId;
            return (
              <div
                key={node.request_id + vi.index}
                className={cn(
                  'absolute left-0 flex items-stretch border-b border-stone-100',
                  isSel ? 'bg-amber-50/60' : isHov ? 'bg-stone-50' : 'bg-white',
                )}
                style={{
                  top: vi.start,
                  height: ROW_H,
                  width: contentW,
                }}
                onClick={() => {
                  select(node.request_id);
                  onSelect?.(node);
                }}
                onMouseEnter={() => hover(node.request_id)}
                onMouseLeave={() => hover(null)}
              >
                {/* label 列：sticky 固定在左 */}
                <div
                  className={cn(
                    'sticky left-0 z-10 flex shrink-0 items-center gap-1 px-1.5',
                    isSel ? 'bg-amber-50/95' : isHov ? 'bg-stone-50' : 'bg-white',
                  )}
                  style={{ width: LABEL_W, paddingLeft: 6 + depth * 12 }}
                >
                  {hasChildren ? (
                    <button
                      type="button"
                      className="rounded p-0.5 text-stone-400 hover:bg-stone-200 hover:text-stone-700"
                      onClick={e => {
                        e.stopPropagation();
                        toggleCollapse(node.request_id);
                      }}
                    >
                      {isCol ? (
                        <ChevronRight className="h-3 w-3" />
                      ) : (
                        <ChevronDown className="h-3 w-3" />
                      )}
                    </button>
                  ) : (
                    <span className="w-4 shrink-0" />
                  )}
                  <span
                    className={cn(
                      'shrink-0 rounded px-1 py-px font-mono text-[9px] uppercase',
                      node.success
                        ? 'bg-stone-100 text-stone-500'
                        : 'bg-rose-50 text-rose-600',
                    )}
                  >
                    {node.observation_type.slice(0, 4)}
                  </span>
                  <span className="truncate text-[11px] text-stone-700">
                    {node.agent_key}
                  </span>
                </div>

                {/* 时间区 */}
                <div className="relative shrink-0" style={{ width: timelineW }}>
                  <GanttBar
                    node={node}
                    bounds={bounds}
                    selected={isSel}
                    hovered={isHov}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
