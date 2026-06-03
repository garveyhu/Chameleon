/** 评测分数的统一展示工具：色编码 + 格式化（贯穿 datasets / eval-jobs 列表/详情/矩阵） */

/** 分数颜色 class：≥0.8 绿 / 0.5–0.8 黄 / <0.5 红 / 无 灰。 */
export const scoreColor = (s: number | null | undefined): string => {
  if (s == null || Number.isNaN(s)) return 'text-stone-400';
  return s >= 0.8
    ? 'text-emerald-600'
    : s >= 0.5
      ? 'text-amber-600'
      : 'text-red-600';
};

/** 分数底色 class（用于 chip / 单元格背景）：≥0.8 绿 / 0.5–0.8 黄 / <0.5 红。 */
export const scoreBg = (s: number | null | undefined): string => {
  if (s == null || Number.isNaN(s)) return 'bg-stone-100 text-stone-400';
  return s >= 0.8
    ? 'bg-emerald-50 text-emerald-700'
    : s >= 0.5
      ? 'bg-amber-50 text-amber-700'
      : 'bg-red-50 text-red-700';
};

/** 0–1 分数 → 两位小数字符串；入参可为后端的 string（Numeric 序列化）。 */
export const formatScore = (
  s: number | string | null | undefined,
): string => {
  if (s == null) return '—';
  const n = typeof s === 'string' ? Number(s) : s;
  return Number.isNaN(n) ? '—' : n.toFixed(2);
};

/** 解析后端 string 分数为 number；无效返回 null（雪花无关，纯小数）。 */
export const parseScore = (
  s: number | string | null | undefined,
): number | null => {
  if (s == null) return null;
  const n = typeof s === 'string' ? Number(s) : s;
  return Number.isNaN(n) ? null : n;
};
