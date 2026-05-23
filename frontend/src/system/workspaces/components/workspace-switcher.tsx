/** Workspace 切换 dropdown —— 顶部 sidebar 之下；admin 看全 "All workspaces"
 *
 * 切换时调 queryClient.clear() 全量 refetch（避免缓存交叉污染）。
 * 切到 "all" 视图 = store 写 null，axios 不带 X-Workspace-Id。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Building2, Check, ChevronsUpDown, Globe, Plus } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/core/components/ui/dropdown-menu';
import { useWorkspaceStore } from '@/core/stores/workspace-store';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import { CreateWorkspaceModal } from '@/system/workspaces/components/create-workspace-modal';
import { workspaceApi } from '@/system/workspaces/services/workspace';
import type {
  CreateWorkspacePayload,
  WorkspaceItem,
} from '@/system/workspaces/types/workspace';

const ALL_LABEL = '所有 workspace';

export const WorkspaceSwitcher: React.FC = () => {
  const qc = useQueryClient();
  const nav = useNavigate();
  const currentId = useWorkspaceStore(s => s.currentId);
  const setCurrent = useWorkspaceStore(s => s.setCurrent);
  const [createOpen, setCreateOpen] = useState(false);

  const listQ = useQuery({
    queryKey: ['workspaces'],
    queryFn: () => workspaceApi.list(),
    staleTime: 30_000,
  });

  const createMut = useMutation({
    mutationFn: (p: CreateWorkspacePayload) => workspaceApi.create(p),
    onSuccess: w => {
      toast.success(`已创建 workspace ${w.workspace_key}`);
      qc.invalidateQueries({ queryKey: ['workspaces'] });
      setCreateOpen(false);
      switchTo(String(w.id));
    },
  });

  const switchTo = (id: string | null) => {
    if (id === currentId) return;
    setCurrent(id);
    qc.clear();
  };

  const currentName = useMemo(() => {
    if (currentId === null) return ALL_LABEL;
    const found = listQ.data?.find(w => String(w.id) === currentId);
    return found?.name ?? `workspace #${currentId}`;
  }, [currentId, listQ.data]);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="mx-3 mb-2 mt-1 flex items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[12px] text-stone-700 transition hover:bg-[var(--color-paper)] hover:shadow-[var(--shadow-soft)]"
          >
            {currentId === null ? (
              <Globe className="h-3.5 w-3.5 flex-shrink-0 text-stone-500" />
            ) : (
              <Building2 className="h-3.5 w-3.5 flex-shrink-0 text-stone-500" />
            )}
            <div className="flex-1 truncate">
              <div className="truncate text-[12.5px] font-medium">
                {currentName}
              </div>
              <div className="text-[10.5px] text-stone-400">
                {currentId === null ? 'admin · 全量视角' : `id=${currentId}`}
              </div>
            </div>
            <ChevronsUpDown className="h-3 w-3 flex-shrink-0 text-stone-400" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56">
          <DropdownMenuLabel className="text-[10.5px] uppercase tracking-wider text-stone-500">
            切换 workspace
          </DropdownMenuLabel>
          <DropdownMenuItem
            onClick={() => switchTo(null)}
            className="flex items-center gap-2 text-[12.5px]"
          >
            <Globe className="h-3.5 w-3.5 text-stone-500" />
            <span className="flex-1">{ALL_LABEL}</span>
            {currentId === null && <Check className="h-3.5 w-3.5 text-emerald-600" />}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          {(listQ.data ?? []).map((w: WorkspaceItem) => {
            const idStr = String(w.id);
            return (
              <DropdownMenuItem
                key={idStr}
                onClick={() => switchTo(idStr)}
                className="flex items-center gap-2 text-[12.5px]"
              >
                <Building2 className="h-3.5 w-3.5 text-stone-500" />
                <span className="flex-1 truncate">
                  {w.name}
                  <span className="ml-1 text-[10.5px] text-stone-400">
                    {w.plan}
                  </span>
                </span>
                {idStr === currentId && (
                  <Check className="h-3.5 w-3.5 text-emerald-600" />
                )}
              </DropdownMenuItem>
            );
          })}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={() => setCreateOpen(true)}
            className="flex items-center gap-2 text-[12.5px] text-primary-700"
          >
            <Plus className="h-3.5 w-3.5" />
            新建 workspace…
          </DropdownMenuItem>
          {currentId !== null && (
            <DropdownMenuItem
              onClick={() => nav(`/workspaces/${currentId}/members`)}
              className="flex items-center gap-2 text-[12.5px]"
            >
              <Building2 className="h-3.5 w-3.5 text-stone-500" />
              管理成员…
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      <CreateWorkspaceModal
        open={createOpen}
        loading={createMut.isPending}
        onClose={() => setCreateOpen(false)}
        onSubmit={p => createMut.mutate(p)}
      />
    </>
  );
};
