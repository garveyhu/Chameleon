/** 极简 markdown → safe HTML 渲染
 *
 * 覆盖常见子集，先 HTML 转义再做内联标记替换，所以 XSS 已经被堵在第一步。
 * 不引外部依赖（marked / DOMPurify 都会显著增大 widget bundle）。
 *
 * 支持：
 *   # / ## / ### 标题
 *   - / * / 1. 列表
 *   > 引用
 *   ```lang ... ``` 代码块
 *   `inline code`
 *   **bold** / __bold__
 *   *italic* / _italic_
 *   [text](url)
 *   段落空行分割
 *   换行 → <br/>
 */

const ESC_MAP: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
};

const esc = (s: string): string => s.replace(/[&<>"']/g, c => ESC_MAP[c] || c);

const URL_OK = /^(https?:|mailto:|\/)/i;

function inline(src: string): string {
  // 先转义全文 —— 后续注入的 tag 都是我们手动拼的，安全
  let s = esc(src);

  // 行内代码 `code`
  s = s.replace(/`([^`\n]+)`/g, (_m, code) => `<code>${code}</code>`);

  // 加粗 **text** / __text__
  s = s.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/__([^_\n]+)__/g, '<strong>$1</strong>');

  // 斜体 *text* / _text_（避免吞掉前面的加粗 token）
  s = s.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
  s = s.replace(/(^|[^_])_([^_\n]+)_(?!_)/g, '$1<em>$2</em>');

  // 链接 [text](url) —— 转义已做过，这里只需要把 URL_OK 的放行
  s = s.replace(
    /\[([^\]]+)\]\(([^)\s]+)\)/g,
    (m, text: string, raw: string) => {
      // 注意 raw 已经被 esc 过，&amp; 要还原一次防止断 URL
      const url = raw.replace(/&amp;/g, '&');
      if (!URL_OK.test(url)) return m;
      const href = url.replace(/"/g, '%22');
      return `<a href="${href}" target="_blank" rel="noopener noreferrer">${text}</a>`;
    },
  );
  return s;
}

interface Block {
  type: 'p' | 'h1' | 'h2' | 'h3' | 'ul' | 'ol' | 'pre' | 'blockquote';
  lines: string[];
  lang?: string;
}

function tokenize(src: string): Block[] {
  const lines = src.replace(/\r\n?/g, '\n').split('\n');
  const blocks: Block[] = [];
  let cur: Block | null = null;
  let inCode = false;

  const flush = () => {
    if (cur) blocks.push(cur);
    cur = null;
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // 围栏代码 ```
    const fenceMatch = line.match(/^```([\w-]*)?\s*$/);
    if (fenceMatch) {
      if (inCode) {
        // 收尾
        flush();
        inCode = false;
        continue;
      }
      flush();
      cur = { type: 'pre', lines: [], lang: fenceMatch[1] || undefined };
      inCode = true;
      continue;
    }
    if (inCode) {
      (cur as Block).lines.push(line);
      continue;
    }

    // 空行：段落分隔
    if (/^\s*$/.test(line)) {
      flush();
      continue;
    }

    // # 标题
    const h = line.match(/^(#{1,3})\s+(.+)$/);
    if (h) {
      flush();
      const level = h[1].length;
      blocks.push({
        type: (level === 1 ? 'h1' : level === 2 ? 'h2' : 'h3') as Block['type'],
        lines: [h[2]],
      });
      continue;
    }

    // 引用 >
    if (/^>\s?/.test(line)) {
      if (!cur || cur.type !== 'blockquote') {
        flush();
        cur = { type: 'blockquote', lines: [] };
      }
      cur.lines.push(line.replace(/^>\s?/, ''));
      continue;
    }

    // 有序列表 1. 2.
    if (/^\d+\.\s+/.test(line)) {
      if (!cur || cur.type !== 'ol') {
        flush();
        cur = { type: 'ol', lines: [] };
      }
      cur.lines.push(line.replace(/^\d+\.\s+/, ''));
      continue;
    }

    // 无序列表 - * +
    if (/^[-*+]\s+/.test(line)) {
      if (!cur || cur.type !== 'ul') {
        flush();
        cur = { type: 'ul', lines: [] };
      }
      cur.lines.push(line.replace(/^[-*+]\s+/, ''));
      continue;
    }

    // 普通段落
    if (!cur || cur.type !== 'p') {
      flush();
      cur = { type: 'p', lines: [] };
    }
    cur.lines.push(line);
  }
  flush();
  return blocks;
}

function render(blocks: Block[]): string {
  return blocks
    .map(b => {
      switch (b.type) {
        case 'pre': {
          const code = b.lines.map(esc).join('\n');
          return `<pre><code${b.lang ? ` data-lang="${esc(b.lang)}"` : ''}>${code}</code></pre>`;
        }
        case 'blockquote':
          return `<blockquote>${b.lines.map(inline).join('<br/>')}</blockquote>`;
        case 'h1':
        case 'h2':
        case 'h3':
          return `<${b.type}>${inline(b.lines.join(' '))}</${b.type}>`;
        case 'ul':
        case 'ol': {
          const items = b.lines.map(l => `<li>${inline(l)}</li>`).join('');
          return `<${b.type}>${items}</${b.type}>`;
        }
        case 'p':
        default:
          return `<p>${b.lines.map(inline).join('<br/>')}</p>`;
      }
    })
    .join('');
}

export function renderMarkdown(src: string): string {
  if (!src) return '';
  return render(tokenize(src));
}
