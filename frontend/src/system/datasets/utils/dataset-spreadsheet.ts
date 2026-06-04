/** 评测样本电子表格（H2）—— 动态列推断 + 单元格取值/写回 helper。
 *
 *  列推断：扫全部 items 的 input_payload，取所有 top-level key 的并集（首次出现顺序）
 *  作为 {{var}} 输入列；再加固定尾列「理想回答 / 元数据」。
 *  单元格形态：兼容采样脱敏嵌套（{hash,preview} 只读）+ 手工扁平文本（可编）两种。 */
import type { DatasetItemRow } from '@/system/datasets/types/dataset';

/** 单元格分类：决定渲染与编辑方式 */
export type CellKind =
  | { kind: 'scalar'; value: string } // string/number/bool → 行内可编辑文本
  | { kind: 'empty' } // 缺该 key / null → 可编辑（填入即创建该 key）
  | { kind: 'redacted'; preview: string } // 采样脱敏 {hash,preview} → 只读灰显
  | { kind: 'json'; text: string }; // 复杂对象/数组 → 点开 JSON 弹层编辑

const EXPECTED_PREFER_KEYS = ['answer', 'output', 'text'] as const;

/** 扫全部 items，并集所有 input_payload 顶层 key，按首次出现顺序排列。 */
export const inferVarKeys = (items: DatasetItemRow[]): string[] => {
  const seen = new Set<string>();
  const keys: string[] = [];
  for (const it of items) {
    const payload = it.input_payload;
    if (!payload || typeof payload !== 'object') continue;
    for (const k of Object.keys(payload)) {
      if (!seen.has(k)) {
        seen.add(k);
        keys.push(k);
      }
    }
  }
  return keys;
};

const isRedactedObject = (v: unknown): v is { preview: string } =>
  v !== null &&
  typeof v === 'object' &&
  !Array.isArray(v) &&
  typeof (v as Record<string, unknown>).preview === 'string';

/** 取 input_payload 某 var key 的单元格形态。 */
export const varCell = (item: DatasetItemRow, key: string): CellKind => {
  const payload = item.input_payload ?? {};
  if (!(key in payload)) return { kind: 'empty' };
  const v = payload[key];
  if (v == null) return { kind: 'empty' };
  if (isRedactedObject(v)) return { kind: 'redacted', preview: v.preview };
  if (typeof v === 'string') return { kind: 'scalar', value: v };
  if (typeof v === 'number' || typeof v === 'boolean') {
    return { kind: 'scalar', value: String(v) };
  }
  return { kind: 'json', text: JSON.stringify(v, null, 2) };
};

/** 写回某 var key 的标量值 → 返回 patch 后的整个 input_payload。 */
export const patchVar = (
  item: DatasetItemRow,
  key: string,
  next: string,
): Record<string, unknown> => ({ ...(item.input_payload ?? {}), [key]: next });

/** 取「理想回答」列的单元格形态：单字段对象取文本，多字段/复杂降级 JSON。 */
export const expectedCell = (item: DatasetItemRow): CellKind => {
  const obj = item.expected_output;
  if (obj == null) return { kind: 'empty' };
  const keys = Object.keys(obj);
  if (keys.length === 0) return { kind: 'empty' };
  if (keys.length === 1) {
    const v = obj[keys[0]];
    if (typeof v === 'string') return { kind: 'scalar', value: v };
    if (typeof v === 'number' || typeof v === 'boolean') {
      return { kind: 'scalar', value: String(v) };
    }
  }
  for (const k of EXPECTED_PREFER_KEYS) {
    const v = obj[k];
    if (typeof v === 'string') return { kind: 'scalar', value: v };
  }
  return { kind: 'json', text: JSON.stringify(obj, null, 2) };
};

/** 写回「理想回答」标量 → expected_output 整体。单字段对象保留原 key，否则包 answer。 */
export const patchExpected = (item: DatasetItemRow, next: string): Record<string, unknown> => {
  const obj = item.expected_output;
  if (obj && Object.keys(obj).length === 1) {
    const k = Object.keys(obj)[0];
    return { [k]: next };
  }
  for (const k of EXPECTED_PREFER_KEYS) {
    if (obj && typeof obj[k] === 'string') return { ...obj, [k]: next };
  }
  return { answer: next };
};

/** 元数据列摘要文案（点开弹层编辑全文）。 */
export const metaSummary = (item: DatasetItemRow): string => {
  const m = item.meta;
  if (!m || Object.keys(m).length === 0) return '';
  return Object.entries(m)
    .filter(([k]) => !k.startsWith('_'))
    .slice(0, 4)
    .map(([k, v]) => `${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`)
    .join(' · ');
};

/** 把单元格 JSON 弹层里的文本解析成对象（用于复杂值/meta 写回）。失败返 null。 */
export const parseJsonObject = (text: string): Record<string, unknown> | null => {
  const t = text.trim();
  if (!t) return null;
  try {
    const j: unknown = JSON.parse(t);
    if (j !== null && typeof j === 'object' && !Array.isArray(j)) {
      return j as Record<string, unknown>;
    }
  } catch {
    return null;
  }
  return null;
};
