/** 端点自动收集 —— glob 扫 registry/*.ts，把所有 default export 的 EndpointSpec[] 合并
 *
 * 新增端点只用在 registry/ 下加 .ts 文件 default export 一个 EndpointSpec[]，
 * 无需修改本文件。
 */
import type { EndpointSpec, GroupMeta } from '@/api-docs/types/endpoint';

import { getGroup, GROUPS } from './_groups';

const modules = import.meta.glob<{ default: EndpointSpec[] }>(
  ['./*.ts', '!./_*.ts'],
  { eager: true },
);

const all: EndpointSpec[] = [];
for (const mod of Object.values(modules)) {
  if (Array.isArray(mod.default)) all.push(...mod.default);
}

/** 校验 id 唯一（dev 环境提醒） */
if (import.meta.env.DEV) {
  const seen = new Set<string>();
  for (const e of all) {
    if (seen.has(e.id)) {
      console.warn(`[api-docs] duplicate endpoint id: ${e.id}`);
    }
    seen.add(e.id);
  }
}

export const ALL_ENDPOINTS: readonly EndpointSpec[] = all;

export interface GroupedEndpoints {
  group: GroupMeta;
  endpoints: EndpointSpec[];
}

/** 按 group 分组 + 排序，给左导航直接渲染 */
export function groupEndpoints(list: readonly EndpointSpec[] = ALL_ENDPOINTS): GroupedEndpoints[] {
  const byGroup = new Map<string, EndpointSpec[]>();
  for (const e of list) {
    const arr = byGroup.get(e.group) ?? [];
    arr.push(e);
    byGroup.set(e.group, arr);
  }

  const groups: GroupedEndpoints[] = [];
  // 先按注册顺序产出
  for (const g of GROUPS) {
    const eps = byGroup.get(g.key);
    if (eps) {
      groups.push({
        group: g,
        endpoints: [...eps].sort((a, b) => (a.order ?? 100) - (b.order ?? 100)),
      });
      byGroup.delete(g.key);
    }
  }
  // 未注册分组兜底
  for (const [key, eps] of byGroup) {
    groups.push({
      group: getGroup(key),
      endpoints: [...eps].sort((a, b) => (a.order ?? 100) - (b.order ?? 100)),
    });
  }
  return groups;
}

/** 按 id 找端点 */
export function findEndpoint(id: string): EndpointSpec | undefined {
  return ALL_ENDPOINTS.find(e => e.id === id);
}
