/** 分支切换器 ◀ N/M ▶ —— P21.4 PR #67 */

import { ChevronLeft, ChevronRight, GitBranch } from 'lucide-react';

import { cn } from '@/core/lib/cn';
import type { EntityId } from '@/core/types/api';

interface Props {
  siblingIds: EntityId[];
  currentId: EntityId;
  onSelect: (next: EntityId) => void;
  className?: string;
}

export const BranchSwitcher = ({
  siblingIds,
  currentId,
  onSelect,
  className,
}: Props) => {
  if (siblingIds.length <= 1) return null;
  const idx = siblingIds.findIndex(i => String(i) === String(currentId));
  const safeIdx = idx < 0 ? 0 : idx;

  const goPrev = () => {
    if (safeIdx > 0) onSelect(siblingIds[safeIdx - 1]);
  };
  const goNext = () => {
    if (safeIdx < siblingIds.length - 1) onSelect(siblingIds[safeIdx + 1]);
  };

  return (
    <div
      className={cn(
        'inline-flex items-center gap-1 rounded-md border border-stone-200 bg-white px-1.5 py-0.5 text-[11px] text-stone-600',
        className,
      )}
    >
      <GitBranch className="h-3 w-3 text-fuchsia-500" />
      <button
        type="button"
        onClick={goPrev}
        disabled={safeIdx === 0}
        className="rounded p-0.5 hover:bg-stone-100 disabled:opacity-30"
      >
        <ChevronLeft className="h-3 w-3" />
      </button>
      <span className="font-mono tnum">
        {safeIdx + 1} / {siblingIds.length}
      </span>
      <button
        type="button"
        onClick={goNext}
        disabled={safeIdx === siblingIds.length - 1}
        className="rounded p-0.5 hover:bg-stone-100 disabled:opacity-30"
      >
        <ChevronRight className="h-3 w-3" />
      </button>
    </div>
  );
};
