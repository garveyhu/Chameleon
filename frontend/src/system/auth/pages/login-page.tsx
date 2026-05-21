/** 登录页 —— waveflow editorial 双栏复刻
 *
 * 左：editorial 表单 + LeftDecor 几何浮件
 * 右：黑色渐变 + 文案 hero（仅 lg+）
 *
 * 表单用极简下划线 input（与 admin 业务表单的 shadcn 边框 input 区分开）
 */

import { zodResolver } from '@hookform/resolvers/zod';
import { ArrowRight, Eye, EyeOff, Loader2 } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';
import { z } from 'zod';

import { cn } from '@/core/lib/cn';
import { useAuthStore } from '@/core/stores/auth-store';
import { LeftDecor } from '@/system/auth/components/left-decor';

const schema = z.object({
  username: z.string().min(1, '请输入用户名'),
  password: z.string().min(1, '请输入密码'),
});
type FormData = z.infer<typeof schema>;

export const LoginPage = () => {
  const login = useAuthStore(s => s.login);
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

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
    <div className="flex min-h-screen">
      {/* 左：editorial 表单 */}
      <div className="relative flex w-full flex-col overflow-hidden px-8 sm:px-16 lg:w-1/2">
        <LeftDecor />

        <div className="relative z-10 pt-[14vh]">
          {/* hero: 大 logo + Chameleon + 产品定位 */}
          <div className="max-w-[440px]">
            <img
              src="/logo.png"
              alt="Chameleon"
              className="mb-5 h-14 w-14 object-contain"
            />
            <div
              className="text-[28px] font-medium tracking-tight text-stone-900"
              style={{ letterSpacing: '-0.02em' }}
            >
              Chameleon<span className="text-stone-400">.</span>
            </div>
            <div className="mt-1.5 text-[13.5px] text-stone-500">
              AI 服务统一聚合平台 · 管理控制台
            </div>
          </div>

          {/* 表单紧贴 hero */}
          <div className="mt-10 max-w-[440px]">
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
              <div>
                <label className="mb-1 block text-[12px] font-medium text-stone-500">
                  用户名
                </label>
                <input
                  type="text"
                  autoComplete="username"
                  autoFocus
                  placeholder="请输入用户名"
                  {...register('username')}
                  className={cn(
                    'w-full border-b bg-transparent py-2.5 text-[15px] text-stone-900 outline-none transition placeholder:text-stone-400',
                    errors.username
                      ? 'border-red-400 focus:border-red-600'
                      : 'border-stone-300 focus:border-stone-900',
                  )}
                />
                {errors.username && (
                  <div className="mt-1 text-[11.5px] text-red-600">
                    {errors.username.message}
                  </div>
                )}
              </div>

              <div>
                <label className="mb-1 block text-[12px] font-medium text-stone-500">
                  密码
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    placeholder="请输入密码"
                    {...register('password')}
                    className={cn(
                      'w-full border-b bg-transparent py-2.5 pr-8 text-[15px] text-stone-900 outline-none transition placeholder:text-stone-400',
                      errors.password
                        ? 'border-red-400 focus:border-red-600'
                        : 'border-stone-300 focus:border-stone-900',
                    )}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(s => !s)}
                    className="absolute right-0 top-1/2 -translate-y-1/2 rounded p-1 text-stone-400 transition hover:bg-stone-100 hover:text-stone-700"
                    aria-label={showPassword ? '隐藏密码' : '显示密码'}
                  >
                    {showPassword ? (
                      <EyeOff className="h-3.5 w-3.5" />
                    ) : (
                      <Eye className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>
                {errors.password && (
                  <div className="mt-1 text-[11.5px] text-red-600">
                    {errors.password.message}
                  </div>
                )}
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="group inline-flex h-11 min-w-[140px] items-center justify-center gap-2 rounded-full bg-stone-900 px-6 text-[13.5px] tracking-wide text-white transition hover:bg-stone-800 disabled:opacity-60"
              >
                {submitting ? '登录中' : '继续'}
                {submitting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <ArrowRight className="h-3.5 w-3.5 transition group-hover:translate-x-1" />
                )}
              </button>
            </form>
          </div>
        </div>

        <div className="min-h-10 flex-1" />

        <footer className="relative z-10 pb-10 text-[12px] text-stone-400">
          © {new Date().getFullYear()} Chameleon · Open Source
        </footer>
      </div>

      {/* 右：黑色渐变 + 产品文案（仅 lg+） */}
      <div className="relative hidden w-1/2 overflow-hidden lg:block">
        <div
          className="absolute inset-0"
          style={{
            background: 'linear-gradient(135deg, #0a0e1a 0%, #1a1530 50%, #0a1822 100%)',
          }}
        />
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              'radial-gradient(circle at 30% 40%, rgba(14,165,233,0.3), transparent 60%), radial-gradient(circle at 70% 70%, rgba(16,185,129,0.18), transparent 60%)',
          }}
        />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex flex-col p-10 text-white">
          <p
            className="mb-2 text-[11px] tracking-[0.4em] text-white/40"
            style={{ writingMode: 'horizontal-tb' }}
          >
            多源融合 · 智能聚合
          </p>
          <h2
            className="text-[30px] font-light leading-tight tracking-tight"
            style={{ letterSpacing: '-0.01em' }}
          >
            让 AI，
            <span
              className="text-white/85"
              style={{
                fontFamily: 'var(--font-serif)',
                fontStyle: 'italic',
                fontWeight: 400,
              }}
            >
              自如聚合。
            </span>
          </h2>
        </div>
      </div>
    </div>
  );
};
