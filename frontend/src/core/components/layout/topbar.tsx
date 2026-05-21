/** 顶部栏：用户菜单 + 语言切换 */

import { Globe, LogOut, User as UserIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { Button } from '@/core/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/core/components/ui/dropdown-menu';
import { setLanguage } from '@/core/i18n';
import { useAuthStore } from '@/core/stores/auth-store';

export const Topbar = () => {
  const user = useAuthStore(s => s.user);
  const logout = useAuthStore(s => s.logout);
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  const handleLang = (lng: 'zh-CN' | 'en-US') => () => setLanguage(lng);

  return (
    <header className="flex h-14 items-center justify-between border-b border-stone-200 bg-[var(--color-paper)] px-6">
      <div />
      <div className="flex items-center gap-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label={t('topbar.language', '语言')}>
              <Globe className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-36">
            <DropdownMenuItem
              onClick={handleLang('zh-CN')}
              className={i18n.language === 'zh-CN' ? 'bg-stone-100' : ''}
            >
              简体中文
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={handleLang('en-US')}
              className={i18n.language === 'en-US' ? 'bg-stone-100' : ''}
            >
              English
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="gap-2">
              <UserIcon className="h-4 w-4" />
              <span className="font-medium">{user?.display_name || user?.username || '—'}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuLabel className="font-normal">
              <div className="font-medium text-stone-900">{user?.username}</div>
              <div className="text-xs text-stone-500">{user?.email || '—'}</div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => navigate('/change-password')}>
              {t('topbar.change_password', '修改密码')}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={handleLogout} className="text-red-600">
              <LogOut className="mr-2 h-4 w-4" /> {t('topbar.logout', '退出登录')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
};
