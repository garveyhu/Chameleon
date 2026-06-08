/** 评测样本电子表格列元数据 —— 列名中文映射 + 列分类 + 列宽。
 *
 * 电子表格表头原先甩 input_payload 的原始 key（user_input / hash / token_count …），
 * 阅读感差。这里给常见 key 一份友好中文标签 + 语义分类，让表头可读、系统列可隐、列宽分层。
 *
 * 分类语义：
 *  - input  → 业务输入列（用户真正关心的内容，宽列，默认显示）
 *  - system → 采样/统计派生的系统列（hash / length / token_count …，窄列，默认隐藏）
 *  - meta   → 来源 / 溯源类（source / source_call_log_id，中等宽，默认显示）
 *
 * 未知 key 走优雅兜底（不丢信息）：下划线转空格 + 首字母大写，分类按 system 派生名启发式判断。
 */

export type ColumnCategory = 'input' | 'system' | 'meta';

interface ColumnMeta {
  /** 友好中文标签 */
  label: string;
  category: ColumnCategory;
}

/** 已知 key → 中文标签 + 分类。覆盖采样 / 手工导入常见字段。 */
const COLUMN_META: Record<string, ColumnMeta> = {
  // 业务输入
  user_input: { label: '用户输入', category: 'input' },
  query: { label: '查询', category: 'input' },
  question: { label: '问题', category: 'input' },
  input: { label: '输入', category: 'input' },
  prompt: { label: '提示词', category: 'input' },
  text: { label: '文本', category: 'input' },
  content: { label: '内容', category: 'input' },
  context: { label: '上下文', category: 'input' },
  // 系统派生（默认隐藏）
  hash: { label: '哈希', category: 'system' },
  length: { label: '长度', category: 'system' },
  token_count: { label: 'Token 数', category: 'system' },
  tokens: { label: 'Token', category: 'system' },
  char_count: { label: '字符数', category: 'system' },
  // 来源 / 溯源
  source: { label: '来源', category: 'meta' },
  source_call_log_id: { label: '来源调用', category: 'meta' },
};

/** 默认隐藏的系统列 key（让默认视图干净，只留业务输入 + 理想回答 + 元数据）。 */
const DEFAULT_HIDDEN_KEYS: ReadonlySet<string> = new Set(['hash', 'length', 'token_count']);

/** 列宽（px）按分类分层：系统列窄、业务文本宽，避免所有列挤同宽。 */
export const COLUMN_WIDTH: Record<ColumnCategory, number> = {
  system: 100,
  meta: 160,
  input: 240,
};

/** 固定尾列宽度。 */
export const EXPECTED_COL_WIDTH = 220;
export const META_COL_WIDTH = 200;
export const NOTE_COL_WIDTH = 220;

/** 下划线 / 连字符转空格 + 每词首字母大写（未知英文 key 的轻量美化，不丢信息）。 */
const prettify = (key: string): string =>
  key
    .replace(/[_-]+/g, ' ')
    .trim()
    .replace(/\b\w/g, c => c.toUpperCase());

/** 取列友好标签；未知 key 优雅兜底为美化后的原 key。 */
export const getColumnLabel = (key: string): string => COLUMN_META[key]?.label ?? prettify(key);

/** 取列语义分类；未知 key 按后缀启发式判断（统计派生 → system，其余 → input）。 */
export const getColumnCategory = (key: string): ColumnCategory => {
  const known = COLUMN_META[key];
  if (known) return known.category;
  if (/(_count|_id|_hash|_length|_len|_tokens?)$/.test(key)) return 'system';
  if (key === 'id') return 'system';
  return 'input';
};

/** 取列宽（px），按分类分层。 */
export const getColumnWidth = (key: string): number => COLUMN_WIDTH[getColumnCategory(key)];

/** 该列是否默认隐藏（仅显式列入的系统列）。 */
export const isDefaultHidden = (key: string): boolean => DEFAULT_HIDDEN_KEYS.has(key);

/** 从全部动态列里挑出默认隐藏的那批（用于初始化 hiddenColumns）。 */
export const defaultHiddenColumns = (keys: string[]): string[] =>
  keys.filter(isDefaultHidden);
