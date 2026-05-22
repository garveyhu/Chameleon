/** 智能导航：预取数据 + 200ms 内有返回再切页（避免目标页 skeleton 一闪）
 *
 * 用法：
 *   const smartNav = useSmartNavigate();
 *   onRowClick={k =>
 *     smartNav(`/kbs/${k.id}`, {
 *       prefetch: () =>
 *         qc.prefetchQuery({ queryKey: ['kb', k.id], queryFn: () => kbApi.get(k.id) }),
 *     })
 *   }
 *
 * 行为：
 *   - 没有 prefetch：等同于 navigate(to)，立即切
 *   - 有 prefetch：等 prefetch 或 maxDelayMs（默认 200）任一完成；期间
 *     顶部出 NavProgressBar 反馈
 *   - 切走后由目标页面 useQuery 取缓存，没缓存则按目标页面的 loading 逻辑走
 */

import { useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';
import { useNavigate, type NavigateOptions } from 'react-router-dom';

import { useNavPendingStore } from '@/core/stores/nav-pending-store';

interface SmartNavigateOptions extends NavigateOptions {
  /** 预取一个或多个 Query；建议传 qc.prefetchQuery 调用结果。多个用数组。 */
  prefetch?: () => Promise<unknown> | Array<() => Promise<unknown>>;
  /** 最长等待预取的时间；默认 200ms。超过仍切走。 */
  maxDelayMs?: number;
}

export function useSmartNavigate() {
  const navigate = useNavigate();
  const begin = useNavPendingStore(s => s.begin);
  const end = useNavPendingStore(s => s.end);

  return useCallback(
    async (to: string, opts: SmartNavigateOptions = {}) => {
      const { prefetch, maxDelayMs = 200, ...navOpts } = opts;
      if (!prefetch) {
        navigate(to, navOpts);
        return;
      }
      begin();
      try {
        const promise =
          typeof prefetch === 'function'
            ? prefetch()
            : Promise.all((prefetch as Array<() => Promise<unknown>>).map(p => p()));
        await Promise.race([
          promise,
          new Promise(resolve => setTimeout(resolve, maxDelayMs)),
        ]);
      } finally {
        end();
        navigate(to, navOpts);
      }
    },
    [navigate, begin, end],
  );
}

/** 便利 hook：暴露 qc 给调用方组合 prefetch */
export function useQc() {
  return useQueryClient();
}
