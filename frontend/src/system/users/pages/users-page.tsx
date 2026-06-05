/** 用户管理页 —— 现代卡片网格 */

import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, UserCheck, Users as UsersIcon, UserX } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';

import { ConfirmDialog } from '@/core/components/common/confirm-dialog';
import { EmptyState } from '@/core/components/common/empty-state';
import { MiniStat } from '@/core/components/common/mini-stat';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { Label } from '@/core/components/ui/label';
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { UserCard } from '@/system/users/components/user-card';
import { userApi } from '@/system/users/services/user';
import type { UserItem } from '@/system/users/types/user';

const createSchema = z.object({
  username: z.string().min(1, '用户名必填').max(64),
  password: z.string().min(8, '至少 8 位'),
  email: z.string().email('邮箱格式错误').or(z.literal('')).optional(),
  display_name: z.string().max(128).optional(),
  role_codes_raw: z.string().optional(),
});
type CreateForm = z.infer<typeof createSchema>;

const resetSchema = z.object({
  new_password: z.string().min(8),
});
type ResetForm = z.infer<typeof resetSchema>;

export const UsersPage = () => {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [resetUser, setResetUser] = useState<UserItem | null>(null);
  const [deleteUser, setDeleteUser] = useState<UserItem | null>(null);

  const listQ = useQuery({
    queryKey: ['users'],
    queryFn: () => userApi.list({ page: 1, page_size: 100 }),
  });

  const createMut = useMutation({
    mutationFn: (req: CreateForm) =>
      userApi.create({
        username: req.username,
        password: req.password,
        email: req.email || undefined,
        display_name: req.display_name || undefined,
        role_codes: req.role_codes_raw
          ? req.role_codes_raw
              .split(',')
              .map(s => s.trim())
              .filter(Boolean)
          : [],
      }),
    onSuccess: () => {
      toast.success('用户已创建');
      qc.invalidateQueries({ queryKey: ['users'] });
      setCreateOpen(false);
    },
  });

  const resetMut = useMutation({
    mutationFn: (args: { id: EntityId; req: ResetForm }) =>
      userApi.resetPassword(args.id, { new_password: args.req.new_password }),
    onSuccess: () => {
      toast.success('密码已重置');
      setResetUser(null);
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: EntityId) => userApi.delete(id),
    onSuccess: () => {
      toast.success('用户已删除');
      qc.invalidateQueries({ queryKey: ['users'] });
      setDeleteUser(null);
    },
  });

  const users = listQ.data?.items || [];
  const activeCount = users.filter(u => u.status === 'active').length;

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-[16px] font-semibold text-stone-900">
            {t('page.users_title')}
          </h1>
          <p className="mt-0.5 text-[12px] text-stone-500">平台账号 —— 角色、状态与密码在此管理</p>
        </div>
        <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="h-3.5 w-3.5" /> {t('common.create')}
        </Button>
      </header>

      <div className="grid grid-cols-3 gap-3">
        <MiniStat label="用户总数" value={users.length} icon={UsersIcon} tone="primary" />
        <MiniStat label="活跃" value={activeCount} icon={UserCheck} tone="success" />
        <MiniStat label="停用" value={users.length - activeCount} icon={UserX} tone="neutral" />
      </div>

      {listQ.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="h-[148px] animate-pulse rounded-xl border border-stone-200 bg-stone-50"
            />
          ))}
        </div>
      ) : users.length === 0 ? (
        <EmptyState
          icon={<UsersIcon strokeWidth={1.5} />}
          title={t('empty.users')}
          action={
            <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> {t('common.create')}
            </Button>
          }
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {users.map(u => (
            <UserCard
              key={String(u.id)}
              user={u}
              onReset={() => setResetUser(u)}
              onDelete={() => setDeleteUser(u)}
            />
          ))}
        </div>
      )}

      <CreateUserModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={data => createMut.mutate(data)}
        loading={createMut.isPending}
      />

      <ResetPasswordModal
        user={resetUser}
        onClose={() => setResetUser(null)}
        onSubmit={data => resetUser && resetMut.mutate({ id: resetUser.id, req: data })}
        loading={resetMut.isPending}
      />

      <ConfirmDialog
        open={!!deleteUser}
        title="删除用户"
        description={`确定删除用户 ${deleteUser?.username}？该用户所有会话会立即失效。`}
        variant="danger"
        confirmText="删除"
        onConfirm={() => deleteUser && deleteMut.mutate(deleteUser.id)}
        onCancel={() => setDeleteUser(null)}
      />
    </div>
  );
};

// ── 局部子组件 ─────────────────────────────────────────────

const CreateUserModal = ({
  open,
  onClose,
  onSubmit,
  loading,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: CreateForm) => void;
  loading: boolean;
}) => {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CreateForm>({ resolver: zodResolver(createSchema) });
  return (
    <Modal
      open={open}
      onOpenChange={o => {
        if (!o) {
          reset();
          onClose();
        }
      }}
    >
      <ModalContent size="md">
        <ModalHeader>
          <ModalTitle>新建用户</ModalTitle>
        </ModalHeader>
        <form
          onSubmit={handleSubmit(d => {
            onSubmit(d);
            reset();
          })}
          className="flex flex-1 flex-col overflow-hidden"
        >
          <ModalBody className="space-y-4">
            <Field label="用户名 *" error={errors.username?.message}>
              <Input {...register('username')} />
            </Field>
            <Field label="密码 *" error={errors.password?.message}>
              <Input type="password" {...register('password')} />
            </Field>
            <Field label="邮箱" error={errors.email?.message}>
              <Input type="email" {...register('email')} />
            </Field>
            <Field label="显示名">
              <Input {...register('display_name')} />
            </Field>
            <Field label="角色（逗号分隔，如 admin,developer）">
              <Input {...register('role_codes_raw')} placeholder="viewer" />
            </Field>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" type="button" onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? '创建中...' : '创建'}
            </Button>
          </ModalFooter>
        </form>
      </ModalContent>
    </Modal>
  );
};

const ResetPasswordModal = ({
  user,
  onClose,
  onSubmit,
  loading,
}: {
  user: UserItem | null;
  onClose: () => void;
  onSubmit: (data: ResetForm) => void;
  loading: boolean;
}) => {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ResetForm>({ resolver: zodResolver(resetSchema) });
  return (
    <Modal
      open={!!user}
      onOpenChange={o => {
        if (!o) {
          reset();
          onClose();
        }
      }}
    >
      <ModalContent size="sm">
        <ModalHeader>
          <ModalTitle>重置密码 · {user?.username}</ModalTitle>
        </ModalHeader>
        <form
          onSubmit={handleSubmit(d => {
            onSubmit(d);
            reset();
          })}
          className="flex flex-1 flex-col overflow-hidden"
        >
          <ModalBody className="space-y-4">
            <Field label="新密码（至少 8 位）" error={errors.new_password?.message}>
              <Input type="password" {...register('new_password')} />
            </Field>
            <p className="text-xs text-amber-700">
              重置后用户会被强制下次登录改密；旧 token 立即失效。
            </p>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" type="button" onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? '提交中...' : '确认重置'}
            </Button>
          </ModalFooter>
        </form>
      </ModalContent>
    </Modal>
  );
};

const Field = ({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) => (
  <div className="space-y-1.5">
    <Label>{label}</Label>
    {children}
    {error && <p className="text-xs text-red-600">{error}</p>}
  </div>
);
