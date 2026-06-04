/** System Prompt 模板变量纯函数工具 —— 单一职责，无副作用、无 React 依赖，可单测。
 *
 * 变量声明源 = System Prompt 文本里的 {{name}} 占位符。
 * extractVars 抽取去重变量名（保序）；fillTemplate 把占位符替换成填的值，
 * 未填的保留原占位符（不静默清空，用户从回答可见漏填）。
 */

/** 变量名匹配：字母 / 数字 / 下划线 / 中文，前后允许空白。 */
const VAR_RE = /\{\{\s*([a-zA-Z0-9_一-龥]+)\s*\}\}/g;

/** 抽取 System Prompt 里的 {{name}} 变量名，去重保序。 */
export function extractVars(text: string): string[] {
  if (!text) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const m of text.matchAll(VAR_RE)) {
    const name = m[1];
    if (!seen.has(name)) {
      seen.add(name);
      out.push(name);
    }
  }
  return out;
}

/** 把 {{name}} 替换成 values[name]；未填（空 / 缺）保留原占位符原样。 */
export function fillTemplate(text: string, values: Record<string, string>): string {
  if (!text) return text;
  return text.replace(VAR_RE, (whole, name: string) => {
    const v = values[name];
    return v != null && v !== '' ? v : whole;
  });
}
