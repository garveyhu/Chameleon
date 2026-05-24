/** 空间管理列表页 —— /workspaces
 *
 * 卡片网格（非传统表格）：列出所有 workspace，支持新建 / 进入成员管理 / 编辑配置 / 删除。
 * 默认 workspace（id=1）不可删除。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Boxes, Plus, SlidersHorizontal, Trash2, Users2 } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { ConfirmDialog } from '@/core/components/common/confirm-dialog';
import { EmptyState } from '@/core/components/common/empty-state';
import { SectionCard } from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { formatRelative } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { CreateWorkspaceModal } from '@/system/workspaces/components/create-workspace-modal';
import { WorkspaceConfigSheet } from '@/system/workspaces/components/workspace-config-sheet';
import { workspaceApi } from '@/system/workspaces/services/workspace';
import type {
  WorkspaceItem,
  WorkspacePlan,
} from '@/system/workspaces/types/workspace';
import { DEFAULT_WORKSPACE_ID } from '@/system/workspaces/types/workspace';

const PLAN_STYLE: Record<WorkspacePlan, string> = {
  free: 'bg-stone-100 text-stone-600',
  pro: 'bg-sky-50 text-sky-700',
  enterprise: 'bg-amber-50 text-amber-700',
};

export const WorkspacesPage = () => {
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [editWs, setEditWs] = useState<WorkspaceItem | null>(null);
  const [delWs, setDelWs] = useState<WorkspaceItem | null>(null);

  const listQ = useQuery({ queryKey: ['workspaces'], queryFn: workspaceApi.list });

  const createMut = useMutation({
    mutationFn: workspaceApi.create,
    onSuccess: () => {
      toast.success('空间已创建');
      qc.invalidateQueries({ queryKey: ['workspaces'] });
      setCreateOpen(false);
    },
    onError: (e: unknown) => toast.error((e as { message?: string })?.message || '创建失败'),
  });

  const delMut = useMutation({
    mutationFn: (id: EntityId) => workspaceApi.delete(id),
    onSuccess: () => {
      toast.success('已删除');
      qc.invalidateQueries({ queryKey: ['workspaces'] });
      setDelWs(null);
    },
    onError: (e: unknown) => toast.error((e as { message?: string })?.message || '删除失败'),
  });

  const workspaces = listQ.data ?? [];

  return (
    <div>
      <SectionCard>
        <header className="mb-4 flex items-center justify-between">
          <div>
            <h1 className="text-[15px] font-medium text-stone-900">空间管理</h1>
            <p className="mt-0.5 text-[11.5px] text-stone-500">
              每个 workspace 是独立的资源 / 配额 / 成员边界
            </p>
          </div>
          <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="h-3.5 w-3.5" /> 新建空间
          </Button>
        </header>

        {listQ.isLoading ? (
          <div className="py-12 text-center text-[12px] text-stone-400">加载中…</div>
        ) : workspaces.length === 0 ? (
          <EmptyState
            icon={<Boxes strokeWidth={1.5} />}
            title="还没有空间"
            description="新建一个 workspace 来隔离不同团队 / 项目的资源与配额。"
            action={
              <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
                <Plus className="h-3.5 w-3.5" /> 新建空间
              </Button>
            }
          />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {workspaces.map(ws => {
              const isDefault = String(ws.id) === DEFAULT_WORKSPACE_ID;
              return (
                <div
                  key={String(ws.id)}
                  className="flex flex-col rounded-xl border border-stone-200 bg-[var(--color-paper)] p-5 transition hover:border-stone-300 hover:shadow-pop"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2.5">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-50 text-amber-600">
                        <Boxes className="h-4 w-4" strokeWidth={1.75} />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="truncate text-[14px] font-medium text-stone-900">
                            {ws.name}
                          </span>
                          {isDefault && (
                            <span className="shrink-0 rounded bg-stone-100 px-1.5 py-0.5 text-[10px] text-stone-500">
                              默认
                            </span>
                          )}
                        </div>
                        <div className="truncate font-mono text-[11px] text-stone-400">
                          {ws.workspace_key}
                        </div>
                      </div>
                    </div>
                    <Badge variant="outline" className={`shrink-0 ${PLAN_STYLE[ws.plan]}`}>
                      {ws.plan}
                    </Badge>
                  </div>

                  <div className="mt-4 text-[11px] text-stone-400">
                    创建于 {formatRelative(ws.created_at)}
                  </div>

                  <div className="mt-4 flex items-center gap-0.5 border-t border-stone-100 pt-3">
                    <Link
                      to={`/workspaces/${ws.id}/members`}
                      className="inline-flex items-center gap-1 whitespace-nowrap rounded px-2 py-1 text-[11.5px] text-stone-600 hover:bg-stone-100 hover:text-stone-900"
                    >
                      <Users2 className="h-3.5 w-3.5" /> 成员
                    </Link>
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 whitespace-nowrap rounded px-2 py-1 text-[11.5px] text-stone-600 hover:bg-stone-100 hover:text-stone-900"
                      onClick={() => setEditWs(ws)}
                    >
                      <SlidersHorizontal className="h-3.5 w-3.5" /> 配置
                    </button>
                    <div className="flex-1" />
                    <button
                      type="button"
                      title={isDefault ? '默认空间不可删除' : '删除空间'}
                      disabled={isDefault}
                      className="shrink-0 rounded p-1 text-stone-500 hover:bg-red-100 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-stone-500"
                      onClick={() => setDelWs(ws)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </SectionCard>

      <CreateWorkspaceModal
        open={createOpen}
        loading={createMut.isPending}
        onClose={() => setCreateOpen(false)}
        onSubmit={createMut.mutate}
      />
      <WorkspaceConfigSheet workspace={editWs} onClose={() => setEditWs(null)} />
      <ConfirmDialog
        open={!!delWs}
        title="删除空间"
        description={
          delWs
            ? `删除「${delWs.name}」后，其下成员关系、配额与引用该空间的资源都将失效。此操作不可恢复。`
            : ''
        }
        variant="danger"
        confirmText="删除"
        onConfirm={() => delWs && delMut.mutate(delWs.id)}
        onCancel={() => setDelWs(null)}
      />
    </div>
  );
};
