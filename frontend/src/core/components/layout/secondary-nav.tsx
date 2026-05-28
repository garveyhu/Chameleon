/** 二级导航 —— 无边左导航（与内容同表面）
 *
 * 展示当前域（由路由推断）的分组与叶子项。
 * 选中态：浅蓝药丸 + 左侧书签竖条（带微光），无边框、不另起底色。
 */
import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router-dom';

import { activeLeafTo, findActiveDomain, type NavLeaf } from '@/core/components/layout/nav-config';
import { cn } from '@/core/lib/cn';
import { useAuthStore } from '@/core/stores/auth-store';

export const SecondaryNav = () => {
  const { pathname } = useLocation();
  const { t } = useTranslation();
  const hasPermission = useAuthStore(s => s.hasPermission);

  const domain = findActiveDomain(pathname);
  const visibleLeaves = (leaves: NavLeaf[]) => leaves.filter(l => !l.perm || hasPermission(l.perm));

  // 当前域全部可见叶子合起来算"唯一选中"（跨分组也只亮一个）
  const allVisible = domain.groups.flatMap(g => visibleLeaves(g.children));
  const activeTo = activeLeafTo(pathname, allVisible);

  // 单项域（如知识库）无需左导航——顶部 tab 已表明所在域，内容直接铺满
  if (allVisible.length <= 1) return null;

  const groups = domain.groups
    .map(g => ({ ...g, children: visibleLeaves(g.children) }))
    .filter(g => g.children.length > 0);

  return (
    <aside className="flex w-56 flex-shrink-0 flex-col overflow-y-auto bg-[var(--color-warm)] px-3 py-4">
      {groups.map((g, i) => (
        <div key={g.i18nKey}>
          <div
            className={cn(
              'px-3 pb-1.5 text-[10.5px] font-bold tracking-[0.06em] text-stone-400 uppercase',
              i === 0 ? 'pt-0' : 'pt-5',
            )}
          >
            {t(g.i18nKey, g.fallbackTitle)}
          </div>
          {g.children.map(leaf => (
            <LeafItem key={leaf.to} leaf={leaf} active={leaf.to === activeTo} />
          ))}
        </div>
      ))}
    </aside>
  );
};

const LeafItem = ({ leaf, active }: { leaf: NavLeaf; active: boolean }) => {
  const Icon = leaf.icon;
  const { t } = useTranslation();
  return (
    <Link
      to={leaf.to}
      className={cn(
        'relative flex items-center gap-3 rounded-[10px] px-3 py-2 text-[13px] font-medium transition',
        active
          ? 'bg-blue-50 font-semibold text-blue-700'
          : 'text-stone-600 hover:bg-stone-200/40 hover:text-stone-900',
      )}
    >
      {/* 选中书签竖条（借鉴磨砂版）*/}
      {active && (
        <span className="absolute top-2 bottom-2 left-0 w-[3px] rounded-r-[3px] bg-blue-600 shadow-[0_0_8px_rgba(59,130,246,0.45)]" />
      )}
      <Icon className={cn('h-4 w-4 flex-shrink-0', active ? 'text-blue-600' : 'text-stone-400')} />
      <span className="flex-1 truncate">{t(leaf.i18nKey, leaf.fallbackTitle)}</span>
    </Link>
  );
};
