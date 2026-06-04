/** GSB verdict 展示映射（复用） —— G/S/B → 中文标签 + 徽章配色。
 *  纯函数，独立成文件避免 react-refresh/only-export-components 限制。 */

export interface VerdictMeta {
  label: string;
  variant: 'success' | 'warning' | 'danger';
}

const VERDICT_META: Record<string, VerdictMeta> = {
  G: { label: '好', variant: 'success' },
  S: { label: '平', variant: 'warning' },
  B: { label: '差', variant: 'danger' },
};

export const verdictOf = (
  fs: Record<string, number | string | null> | null | undefined,
): VerdictMeta | null => {
  const v = fs?.verdict;
  if (typeof v !== 'string') return null;
  return VERDICT_META[v] ?? null;
};
