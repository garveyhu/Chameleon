/** 首次登录强制改密页 */

import { zodResolver } from '@hookform/resolvers/zod';
import { KeyRound } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';
import { toast } from '@/core/lib/toast';
import { z } from 'zod';

import { Spinner } from '@/core/components/common/spinner';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { Label } from '@/core/components/ui/label';
import { authApi } from '@/core/services/auth';
import { useAuthStore } from '@/core/stores/auth-store';

const schema = z
  .object({
    new_password: z.string().min(8, '密码至少 8 位').max(255),
    confirm: z.string().min(1, '请确认密码'),
  })
  .refine(d => d.new_password === d.confirm, {
    path: ['confirm'],
    message: '两次输入不一致',
  });

type FormData = z.infer<typeof schema>;

export const FirstPasswordPage = () => {
  const user = useAuthStore(s => s.user);
  const logout = useAuthStore(s => s.logout);
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: FormData) => {
    setSubmitting(true);
    try {
      await authApi.firstChangePassword({ new_password: data.new_password });
      toast.success('密码已修改，请用新密码重新登录');
      await logout();
      navigate('/login', { replace: true });
    } catch (e) {
      console.debug('first change password failed', e);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex h-screen items-center justify-center bg-[var(--color-warm)]">
      <div className="w-[420px] rounded-xl border border-stone-200 bg-[var(--color-paper)] p-10 shadow-pop">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-amber-500 font-serif text-white shadow-card">
            <KeyRound className="h-6 w-6" />
          </div>
          <h1 className="font-serif text-xl text-stone-900">设置新密码</h1>
          <p className="mt-1 text-xs text-stone-500">
            欢迎 {user?.username}，首次登录需要修改密码
          </p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="new_password">新密码（至少 8 位）</Label>
            <Input
              id="new_password"
              type="password"
              autoComplete="new-password"
              {...register('new_password')}
            />
            {errors.new_password && (
              <p className="text-xs text-red-600">{errors.new_password.message}</p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirm">确认密码</Label>
            <Input
              id="confirm"
              type="password"
              autoComplete="new-password"
              {...register('confirm')}
            />
            {errors.confirm && <p className="text-xs text-red-600">{errors.confirm.message}</p>}
          </div>
          <Button type="submit" disabled={submitting} className="w-full">
            {submitting && <Spinner size="sm" className="text-white" />}
            {submitting ? '提交中...' : '修改密码'}
          </Button>
        </form>
      </div>
    </div>
  );
};
