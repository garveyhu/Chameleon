/** 登录页 */

import { zodResolver } from '@hookform/resolvers/zod';
import { LogIn } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';
import { z } from 'zod';

import { Spinner } from '@/core/components/common/spinner';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { Label } from '@/core/components/ui/label';
import { useAuthStore } from '@/core/stores/auth-store';

const schema = z.object({
  username: z.string().min(1, '请输入用户名'),
  password: z.string().min(1, '请输入密码'),
});
type FormData = z.infer<typeof schema>;

export const LoginPage = () => {
  const login = useAuthStore(s => s.login);
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
      const user = await login(data);
      if (user.must_change_password) {
        navigate('/first-change-password', { replace: true });
      } else {
        navigate('/dashboard', { replace: true });
      }
    } catch (e) {
      console.debug('login failed', e);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="flex h-screen items-center justify-center"
      style={{
        background:
          'radial-gradient(at 30% 20%, var(--color-primary-100) 0%, transparent 50%), radial-gradient(at 70% 80%, var(--color-warm-2) 0%, transparent 50%), var(--color-warm)',
      }}
    >
      <div className="w-[420px] rounded-xl border border-stone-200 bg-[var(--color-paper)] p-10 shadow-pop">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-primary-600 font-serif text-2xl text-white shadow-card">
            C
          </div>
          <h1 className="font-serif text-2xl text-stone-900">Chameleon</h1>
          <p className="mt-1 text-xs text-stone-500">AI 服务统一接入层 · 管理控制台</p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="username">用户名</Label>
            <Input id="username" autoComplete="username" {...register('username')} />
            {errors.username && <p className="text-xs text-red-600">{errors.username.message}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">密码</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              {...register('password')}
            />
            {errors.password && <p className="text-xs text-red-600">{errors.password.message}</p>}
          </div>
          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? (
              <Spinner size="sm" className="text-white" />
            ) : (
              <LogIn className="h-4 w-4" />
            )}
            {submitting ? '登录中...' : '登录'}
          </Button>
        </form>

        <p className="mt-6 text-center text-xs text-stone-400">忘记密码？管理员可在系统中重置</p>
      </div>
    </div>
  );
};
