/** 用户管理页 */

import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { KeyRound, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { z } from 'zod';

import { ConfirmDialog } from '@/core/components/common/confirm-dialog';
import { DataTable, type DataTableColumn } from '@/core/components/common/data-table';
import { PageHeader } from '@/core/components/common/page-header';
import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { Label } from '@/core/components/ui/label';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/core/components/ui/sheet';
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
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const [createOpen, setCreateOpen] = useState(false);
  const [resetUser, setResetUser] = useState<UserItem | null>(null);
  const [deleteUser, setDeleteUser] = useState<UserItem | null>(null);

  const listQ = useQuery({
    queryKey: ['users', page],
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
    mutationFn: (args: { id: number; req: ResetForm }) =>
      userApi.resetPassword(args.id, { new_password: args.req.new_password }),
    onSuccess: () => {
      toast.success('密码已重置');
      setResetUser(null);
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => userApi.delete(id),
    onSuccess: () => {
      toast.success('用户已删除');
      qc.invalidateQueries({ queryKey: ['users'] });
      setDeleteUser(null);
    },
  });

  const columns: DataTableColumn<UserItem>[] = [
    { key: 'username', title: '用户名' },
    { key: 'display_name', title: '显示名', render: u => u.display_name || '—' },
    { key: 'email', title: '邮箱', render: u => u.email || '—' },
    {
      key: 'roles',
      title: '角色',
      render: u => (
        <div className="flex flex-wrap gap-1">
          {u.role_codes.map(r => (
            <Badge key={r} variant="primary">
              {r}
            </Badge>
          ))}
        </div>
      ),
    },
    {
      key: 'status',
      title: '状态',
      render: u => (
        <Badge variant={u.status === 'active' ? 'success' : 'danger'}>
          {u.status === 'active' ? '活跃' : '禁用'}
        </Badge>
      ),
    },
    {
      key: 'last_login_at',
      title: '最后登录',
      render: u => <span className="text-xs text-stone-500">{formatDateTime(u.last_login_at)}</span>,
    },
    {
      key: 'actions',
      title: '操作',
      align: 'right',
      width: '180px',
      render: u => (
        <div className="flex justify-end gap-1">
          <Button size="sm" variant="ghost" onClick={() => setResetUser(u)}>
            <KeyRound className="h-3.5 w-3.5" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="text-red-600 hover:bg-red-50"
            onClick={() => setDeleteUser(u)}
            disabled={u.username === 'admin'}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="用户管理"
        description="管理控制台用户账号 + 角色分配"
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> 新建用户
          </Button>
        }
      />

      <DataTable
        columns={columns}
        data={listQ.data?.items || []}
        loading={listQ.isLoading}
        pagination={{
          page,
          pageSize,
          total: listQ.data?.total || 0,
          onPageChange: setPage,
        }}
      />

      {/* 创建抽屉 */}
      <CreateUserSheet
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={data => createMut.mutate(data)}
        loading={createMut.isPending}
      />

      {/* 重置密码 */}
      <ResetPasswordSheet
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

const CreateUserSheet = ({
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
    <Sheet
      open={open}
      onOpenChange={o => {
        if (!o) {
          reset();
          onClose();
        }
      }}
    >
      <SheetContent>
        <SheetHeader>
          <SheetTitle>新建用户</SheetTitle>
        </SheetHeader>
        <form
          onSubmit={handleSubmit(d => {
            onSubmit(d);
            reset();
          })}
          className="flex flex-1 flex-col"
        >
          <SheetBody className="space-y-4">
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
          </SheetBody>
          <SheetFooter>
            <Button variant="ghost" type="button" onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? '创建中...' : '创建'}
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );
};

const ResetPasswordSheet = ({
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
    <Sheet
      open={!!user}
      onOpenChange={o => {
        if (!o) {
          reset();
          onClose();
        }
      }}
    >
      <SheetContent width="w-[400px]">
        <SheetHeader>
          <SheetTitle>重置密码 · {user?.username}</SheetTitle>
        </SheetHeader>
        <form
          onSubmit={handleSubmit(d => {
            onSubmit(d);
            reset();
          })}
          className="flex flex-1 flex-col"
        >
          <SheetBody className="space-y-4">
            <Field label="新密码（至少 8 位）" error={errors.new_password?.message}>
              <Input type="password" {...register('new_password')} />
            </Field>
            <p className="text-xs text-amber-700">
              重置后用户会被强制下次登录改密；旧 token 立即失效。
            </p>
          </SheetBody>
          <SheetFooter>
            <Button variant="ghost" type="button" onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? '提交中...' : '确认重置'}
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
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
