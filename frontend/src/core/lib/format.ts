/** 时间 / 数字格式化工具 */

import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import 'dayjs/locale/zh-cn';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

export function formatDateTime(s: string | Date | null | undefined): string {
  if (!s) return '—';
  return dayjs(s).format('YYYY-MM-DD HH:mm:ss');
}

export function formatDate(s: string | Date | null | undefined): string {
  if (!s) return '—';
  return dayjs(s).format('YYYY-MM-DD');
}

export function formatRelative(s: string | Date | null | undefined): string {
  if (!s) return '—';
  return dayjs(s).fromNow();
}

/** 阅读感优化的相对时间：用于卡片等"更新于 X 前"的弱时间场景。
 *  比 dayjs.fromNow 的"几秒前/几分钟"更克制、口语：
 *  刚刚 / X 分钟前 / X 小时前 / 昨天 / X 天前 / X 个月前 / X 年前。 */
export function formatRelativeReadable(s: string | Date | null | undefined): string {
  if (!s) return '—';
  const then = dayjs(s);
  if (!then.isValid()) return '—';
  const now = dayjs();
  const sec = now.diff(then, 'second');
  if (sec < 60) return '刚刚'; // 含未来时间 / 时钟漂移的负值兜底
  const min = now.diff(then, 'minute');
  if (min < 60) return `${min} 分钟前`;
  const hour = now.diff(then, 'hour');
  if (hour < 24) return `${hour} 小时前`;
  const day = now.diff(then, 'day');
  if (day === 1) return '昨天';
  if (day < 30) return `${day} 天前`;
  const month = now.diff(then, 'month');
  if (month < 12) return `${month || 1} 个月前`;
  return `${now.diff(then, 'year')} 年前`;
}

export function formatNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  return new Intl.NumberFormat('en-US').format(n);
}

export function formatPercent(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined) return '—';
  return `${(n * 100).toFixed(digits)}%`;
}

export function truncate(s: string | null | undefined, max = 80): string {
  if (!s) return '—';
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

/** 时长：ms → "850ms" / "1.2s" / "1m 5s" */
export function formatDurationMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(s < 10 ? 2 : 1)}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${Math.round(s - m * 60)}s`;
}

/** token 计数：1234 → "1.2k" */
export function formatTokens(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  if (n < 1000) return String(n);
  return `${(n / 1000).toFixed(1)}k`;
}

/** USD 成本：按量级自适应小数位，<$0.01 用更多位 */
export function formatCost(usd: number | null | undefined): string {
  if (usd === null || usd === undefined) return '—';
  if (usd === 0) return '$0';
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  if (usd < 1) return `$${usd.toFixed(3)}`;
  return `$${usd.toFixed(2)}`;
}
