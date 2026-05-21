/** 已登录用户改密页 */

import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { z } from 'zod';

import { PageHeader } from '@/core/components/common/page-header';
import { Spinner } from '@/core/components/common/spinner';
import { Button } from '@/core/components/ui/button';
import { Card, CardContent } from '@/core/components/ui/card';
import { Input } from '@/core/components/ui/input';
import { Label } from '@/core/components/ui/label';
import { authApi } from '@/core/services/auth';
import { useAuthStore } from '@/core/stores/auth-store';

const schema = z
  .object({
    old_password: z.string().min(1, '请输入旧密码'),
    new_password: z.string().min(8, '至少 8 位').max(255),
    confirm: z.string().min(1, '请确认密码'),
  })
  .refine(d => d.new_password === d.confirm, {
    path: ['confirm'],
    message: '两次输入不一致',
  });

type FormData = z.infer<typeof schema>;

export const ChangePasswordPage = () => {
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
      await authApi.changePassword({
        old_password: data.old_password,
        new_password: data.new_password,
      });
      toast.success('密码已修改，请重新登录');
      await logout();
      navigate('/login', { replace: true });
    } catch {
      // toast 已弹
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-xl">
      <PageHeader title="修改密码" description="修改后所有旧 token 立即失效，需重新登录" />
      <Card>
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="old_password">旧密码</Label>
              <Input id="old_password" type="password" {...register('old_password')} />
              {errors.old_password && (
                <p className="text-xs text-red-600">{errors.old_password.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="new_password">新密码（至少 8 位）</Label>
              <Input id="new_password" type="password" {...register('new_password')} />
              {errors.new_password && (
                <p className="text-xs text-red-600">{errors.new_password.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm">确认新密码</Label>
              <Input id="confirm" type="password" {...register('confirm')} />
              {errors.confirm && <p className="text-xs text-red-600">{errors.confirm.message}</p>}
            </div>
            <Button type="submit" disabled={submitting}>
              {submitting && <Spinner size="sm" className="text-white" />}
              {submitting ? '提交中...' : '提交修改'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
};
