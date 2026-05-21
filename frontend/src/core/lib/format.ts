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
