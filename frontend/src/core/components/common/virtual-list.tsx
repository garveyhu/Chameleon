/** 通用虚拟列表（@tanstack/react-virtual）—— 大列表 / 移动端长列表不卡
 *
 * 动态行高（measureElement），可选 stickToBottom（聊天流场景：新增/流式时贴底）。
 * 调用方通过 className 提供滚动容器高度（必须有固定高度才能虚拟化）。
 */

import { useVirtualizer } from '@tanstack/react-virtual';
import { useEffect, useRef } from 'react';

import { cn } from '@/core/lib/cn';

interface VirtualListProps<T> {
  items: T[];
  renderItem: (item: T, index: number) => React.ReactNode;
  getKey: (item: T, index: number) => string | number;
  /** 行高预估（动态测量前的占位），默认 60 */
  estimateSize?: number;
  overscan?: number;
  /** 滚动容器样式（务必含高度，如 h-full / max-h-[...]） */
  className?: string;
  /** 行间距 className（容器 padding 之外的行内间隔靠 renderItem 自管） */
  itemClassName?: string;
  /** 聊天流：items 变化时滚到底 */
  stickToBottom?: boolean;
}

export function VirtualList<T>({
  items,
  renderItem,
  getKey,
  estimateSize = 60,
  overscan = 8,
  className,
  itemClassName,
  stickToBottom = false,
}: VirtualListProps<T>) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => estimateSize,
    overscan,
    getItemKey: index => getKey(items[index], index),
  });

  // 贴底：items 变化时滚到最后一项（聊天新消息 / 流式逐 chunk 追加）。
  // 依赖 items 引用：流式中每次更新都贴底；静态列表 items 不变则不打扰用户上滚。
  useEffect(() => {
    if (stickToBottom && items.length > 0) {
      virtualizer.scrollToIndex(items.length - 1, { align: 'end' });
    }
  }, [stickToBottom, items, virtualizer]);

  return (
    <div ref={scrollRef} className={cn('overflow-y-auto', className)}>
      <div
        className="relative w-full"
        style={{ height: virtualizer.getTotalSize() }}
      >
        {virtualizer.getVirtualItems().map(vi => (
          <div
            key={vi.key}
            data-index={vi.index}
            ref={virtualizer.measureElement}
            className={cn('absolute left-0 top-0 w-full', itemClassName)}
            style={{ transform: `translateY(${vi.start}px)` }}
          >
            {renderItem(items[vi.index], vi.index)}
          </div>
        ))}
      </div>
    </div>
  );
}
