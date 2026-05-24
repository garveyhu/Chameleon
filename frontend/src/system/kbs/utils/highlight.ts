/** 在 content 里给 query 各 token 包 <mark>，先转义 HTML 特殊字符。返回可 dangerouslySetInnerHTML 的串。 */

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function highlight(content: string, query: string): string {
  const escaped = content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  const tokens = Array.from(
    new Set(
      query
        .toLowerCase()
        .split(/[\s,。，；;.!?！？]+/)
        .filter(t => t.length >= 2),
    ),
  );
  if (tokens.length === 0) return escaped;
  // 按长度倒序，避免短 token 抢先匹配
  tokens.sort((a, b) => b.length - a.length);
  const pattern = new RegExp(`(${tokens.map(escapeRegex).join('|')})`, 'gi');
  return escaped.replace(
    pattern,
    '<mark class="bg-amber-100 rounded px-0.5 text-stone-900">$1</mark>',
  );
}
