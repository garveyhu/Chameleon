/** 用户管理页 */

import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { KeyRound, Plus, Trash2, Users as UsersIcon } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { toast } from '@/core/lib/toast';
import { z } from 'zod';

import { ConfirmDialog } from '@/core/components/common/confirm-dialog';
import { EmptyState } from '@/core/components/common/empty-state';
import {
  DataTable,
  type DataTableColumn,
  SectionCard,
  TablePagination,
  TableToolbar,
} from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { StatusBadge } from '@/core/components/ui/status-badge';
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
import { formatDateTime } from '@/core/lib/format';
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
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [createOpen, setCreateOpen] = useState(false);
  const [resetUser, setResetUser] = useState<UserItem | null>(null);
  const [deleteUser, setDeleteUser] = useState<UserItem | null>(null);

  const listQ = useQuery({
    queryKey: ['users', page, pageSize],
    queryFn: () => userApi.list({ page, page_size: pageSize }),
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
    mutationFn: (args: { id: import('@/core/types/api').EntityId; req: ResetForm }) =>
      userApi.resetPassword(args.id, { new_password: args.req.new_password }),
    onSuccess: () => {
      toast.success('密码已重置');
      setResetUser(null);
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: import('@/core/types/api').EntityId) => userApi.delete(id),
    onSuccess: () => {
      toast.success('用户已删除');
      qc.invalidateQueries({ queryKey: ['users'] });
      setDeleteUser(null);
    },
  });

  const columns: DataTableColumn<UserItem>[] = [
    {
      key: 'user',
      header: t('table.username'),
      render: u => {
        const title = u.display_name || u.username;
        const sub = [u.display_name ? `@${u.username}` : null, u.email]
          .filter(Boolean)
          .join(' · ');
        return (
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-stone-100 text-[11px] font-medium text-stone-600">
              {title.slice(0, 1).toUpperCase()}
            </span>
            <div className="min-w-0">
              <div className="truncate text-[13px] font-medium text-stone-900">{title}</div>
              {sub && <div className="truncate text-[11px] text-stone-400">{sub}</div>}
            </div>
          </div>
        );
      },
    },
    {
      key: 'roles',
      header: t('table.roles'),
      width: 220,
      render: u => (
        <div className="flex flex-wrap gap-1">
          {u.role_codes.length ? (
            u.role_codes.map(r => (
              <Badge key={r} variant="primary">
                {r}
              </Badge>
            ))
          ) : (
            <span className="text-[11px] text-stone-400">—</span>
          )}
        </div>
      ),
    },
    {
      key: 'status',
      header: t('common.status'),
      width: 96,
      render: u =>
        u.status === 'active' ? (
          <StatusBadge tone="success">{t('common.active')}</StatusBadge>
        ) : (
          <StatusBadge tone="neutral">{t('common.disabled')}</StatusBadge>
        ),
    },
    {
      key: 'last_login_at',
      header: t('table.last_login'),
      width: 160,
      render: u => <span className="tnum font-mono text-[11.5px] text-stone-500">{formatDateTime(u.last_login_at)}</span>,
    },
    {
      key: 'actions',
      header: t('common.actions'),
      align: 'right',
      width: 100,
      render: u => (
        <div className="inline-flex items-center gap-0.5">
          <button
            type="button"
            title="重置密码"
            className="rounded p-1 text-stone-600 hover:bg-stone-200 hover:text-stone-900"
            onClick={() => setResetUser(u)}
          >
            <KeyRound className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            title="删除"
            className="rounded p-1 text-stone-600 hover:bg-red-100 hover:text-red-600 disabled:opacity-30 disabled:hover:bg-transparent"
            onClick={() => setDeleteUser(u)}
            disabled={u.username === 'admin'}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <SectionCard>
        <TableToolbar
          title={t('page.users_title')}
          extra={
            <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> {t('common.create')}
            </Button>
          }
        />

        <DataTable
          columns={columns}
          rows={listQ.data?.items || []}
          rowKey="id"
          loading={listQ.isLoading}
          leftBar={u => (u.status === 'active' ? 'bg-emerald-400' : 'bg-stone-300')}
          emptyText={
            <EmptyState
              icon={<UsersIcon strokeWidth={1.5} />}
              title={t('empty.users')}
              action={
                <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
                  <Plus className="h-3.5 w-3.5" /> {t('common.create')}
                </Button>
              }
            />
          }
        />

        <TablePagination
          page={page}
          pageSize={pageSize}
          total={listQ.data?.total || 0}
          onPageChange={setPage}
          onPageSizeChange={s => {
            setPageSize(s);
            setPage(1);
          }}
        />
      </SectionCard>

      <CreateUserModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={data => createMut.mutate(data)}
        loading={createMut.isPending}
      />

      <ResetPasswordModal
        user={resetUser}
        onClose={() => setResetUser(null)}
        onSubmit={data =>
          resetUser && resetMut.mutate({ id: resetUser.id, req: data })
        }
        loading={resetMut.isPending}
      />

      {/* 删除确认 */}
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
