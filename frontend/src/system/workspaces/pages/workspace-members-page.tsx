/** Workspace 成员管理页 —— /workspaces/:id/members */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Plus, Trash2, Users2 } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { SectionCard } from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { cn } from '@/core/lib/cn';
import { confirm } from '@/core/lib/confirm';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import { InviteMemberModal } from '@/system/workspaces/components/invite-member-modal';
import { QuotaCard } from '@/system/workspaces/components/quota-card';
import { workspaceApi } from '@/system/workspaces/services/workspace';
import type {
  AddMemberPayload,
  MemberRole,
} from '@/system/workspaces/types/workspace';
import { MEMBER_ROLES } from '@/system/workspaces/types/workspace';

const ROLE_COLOR: Record<MemberRole, string> = {
  owner: 'bg-amber-50 text-amber-700',
  admin: 'bg-violet-50 text-violet-700',
  member: 'bg-sky-50 text-sky-700',
  viewer: 'bg-stone-50 text-stone-600',
};

export const WorkspaceMembersPage = () => {
  const { id } = useParams<{ id: string }>();
  const wsId = id ?? '';
  const qc = useQueryClient();
  const [inviteOpen, setInviteOpen] = useState(false);

  const wsQ = useQuery({
    queryKey: ['workspace', wsId],
    queryFn: () => workspaceApi.get(wsId),
    enabled: !!wsId,
  });

  const membersQ = useQuery({
    queryKey: ['workspace-members', wsId],
    queryFn: () => workspaceApi.listMembers(wsId),
    enabled: !!wsId,
  });

  const inviteMut = useMutation({
    mutationFn: (p: AddMemberPayload) => workspaceApi.addMember(wsId, p),
    onSuccess: m => {
      toast.success(`已添加成员：${m.username ?? m.user_id}`);
      qc.invalidateQueries({ queryKey: ['workspace-members', wsId] });
      setInviteOpen(false);
    },
    onError: (e: unknown) => {
      toast.error((e as { message?: string })?.message || '添加失败');
    },
  });

  const updateRoleMut = useMutation({
    mutationFn: (args: { membershipId: string | number; role: MemberRole }) =>
      workspaceApi.updateMemberRole(wsId, args.membershipId, {
        role: args.role,
      }),
    onSuccess: () => {
      toast.success('已更新角色');
      qc.invalidateQueries({ queryKey: ['workspace-members', wsId] });
    },
    onError: (e: unknown) => {
      toast.error((e as { message?: string })?.message || '更新失败');
    },
  });

  const removeMut = useMutation({
    mutationFn: (membershipId: string | number) =>
      workspaceApi.removeMember(wsId, membershipId),
    onSuccess: () => {
      toast.success('已移除');
      qc.invalidateQueries({ queryKey: ['workspace-members', wsId] });
    },
    onError: (e: unknown) => {
      toast.error((e as { message?: string })?.message || '移除失败');
    },
  });

  if (!wsId) {
    return (
      <SectionCard>
        <div className="p-6 text-sm text-stone-500">非法的 workspace id</div>
      </SectionCard>
    );
  }

  const members = membersQ.data ?? [];
  const excludeIds = new Set(members.map(m => String(m.user_id)));

  return (
    <>
      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <Link
            to="/dashboard"
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12.5px] text-stone-500 hover:bg-stone-100 hover:text-stone-800"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> 返回
          </Link>
          <span className="text-stone-300">/</span>
          <Users2 className="h-3.5 w-3.5 text-stone-500" />
          <span className="text-[15px] font-medium text-stone-900">
            {wsQ.data?.name ?? '加载中…'}
          </span>
          {wsQ.data && (
            <span className="font-mono text-[11.5px] text-stone-500">
              {wsQ.data.workspace_key}
            </span>
          )}
          {wsQ.data && (
            <Badge variant="outline" className="bg-amber-50 text-[10.5px] text-amber-700">
              {wsQ.data.plan}
            </Badge>
          )}
        </div>

        <QuotaCard workspaceId={wsId} />

        <SectionCard>
          <header className="mb-3 flex items-center justify-between">
            <div>
              <h2 className="flex items-center gap-1.5 text-[14px] font-medium text-stone-900">
                成员
              </h2>
              <p className="mt-0.5 text-[11.5px] text-stone-500">
                {members.length} 位 · 控制谁能访问该 workspace 的资源
              </p>
            </div>
            <Button size="sm" onClick={() => setInviteOpen(true)}>
              <Plus className="mr-1 h-3 w-3" /> 添加成员
            </Button>
          </header>

          {membersQ.isLoading ? (
            <div className="py-12 text-center text-[12px] text-stone-400">加载中…</div>
          ) : members.length === 0 ? (
            <div className="py-12 text-center text-[12px] text-stone-400">
              还没有成员；点右上"添加成员"邀请用户
            </div>
          ) : (
            <table className="w-full text-[12.5px]">
              <thead className="text-[11px] uppercase tracking-wider text-stone-500">
                <tr>
                  <th className="px-2 py-2 text-left">用户名</th>
                  <th className="px-2 py-2 text-left">角色</th>
                  <th className="px-2 py-2 text-left">加入时间</th>
                  <th className="px-2 py-2 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {members.map(m => (
                  <tr
                    key={String(m.id)}
                    className="border-t border-stone-200/70"
                  >
                    <td className="px-2 py-2 text-stone-800">
                      <div className="flex items-center gap-2.5">
                        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-stone-100 text-[11px] font-medium text-stone-600">
                          {(m.username ?? `#${m.user_id}`).slice(0, 1).toUpperCase()}
                        </span>
                        <span className="truncate text-[12.5px]">
                          {m.username ?? `#${m.user_id}`}
                        </span>
                      </div>
                    </td>
                    <td className="px-2 py-2">
                      <Select
                        value={m.role}
                        onValueChange={v =>
                          updateRoleMut.mutate({
                            membershipId: m.id,
                            role: v as MemberRole,
                          })
                        }
                      >
                        <SelectTrigger
                          className={cn(
                            'h-7 w-32 text-[11.5px]',
                            ROLE_COLOR[m.role],
                          )}
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {MEMBER_ROLES.map(o => (
                            <SelectItem key={o.value} value={o.value}>
                              {o.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </td>
                    <td className="px-2 py-2 font-mono text-[11px] text-stone-500">
                      {formatDateTime(m.created_at)}
                    </td>
                    <td className="px-2 py-2 text-right">
                      <button
                        type="button"
                        title="移除成员"
                        onClick={async () => {
                          if (
                            await confirm({
                              title: '确认移除？',
                              description: `${m.username ?? `用户 #${m.user_id}`} 将失去 ${wsQ.data?.name ?? '该 workspace'} 的访问权限。`,
                            })
                          ) {
                            removeMut.mutate(m.id);
                          }
                        }}
                        className="rounded p-1 text-stone-400 hover:bg-rose-50 hover:text-rose-600"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </SectionCard>
      </div>

      <InviteMemberModal
        open={inviteOpen}
        loading={inviteMut.isPending}
        excludeUserIds={excludeIds}
        onClose={() => setInviteOpen(false)}
        onSubmit={p => inviteMut.mutate(p)}
      />
    </>
  );
};
