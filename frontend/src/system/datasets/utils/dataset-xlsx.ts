/** 评测样本 Excel/CSV 互转 —— 决策 D2：前端 SheetJS 解析/生成，复用 /bulk-import，PII 后端兜底。
 *  xlsx 用 dynamic import 懒加载，不拖首屏。 */

import type {
  BulkImportItem,
  DatasetItemRow,
} from '@/system/datasets/types/dataset';

const TEMPLATE_HEADERS = ['输入', '理想回答', '元数据(JSON)'] as const;

const loadXLSX = () => import('xlsx');

/** 单字段对象取纯文本（便于非技术用户在表格里读写）；多字段或非字符串回退 JSON */
const cellOf = (
  obj: Record<string, unknown> | null | undefined,
  preferKeys: string[],
): string => {
  if (!obj) return '';
  const keys = Object.keys(obj);
  if (keys.length === 1) {
    const v = obj[keys[0]];
    return typeof v === 'string' ? v : JSON.stringify(v);
  }
  for (const k of preferKeys) {
    const v = obj[k];
    if (typeof v === 'string') return v;
  }
  return JSON.stringify(obj);
};

/** 单元格纯文本/JSON → 对象：是合法 JSON 对象就直接用，否则包成 {wrapKey: 值} */
const parseCell = (
  raw: string,
  wrapKey: string,
): Record<string, unknown> | null => {
  const t = raw.trim();
  if (!t) return null;
  try {
    const j: unknown = JSON.parse(t);
    if (j !== null && typeof j === 'object' && !Array.isArray(j)) {
      return j as Record<string, unknown>;
    }
  } catch {
    // 非 JSON → 当纯文本处理
  }
  return { [wrapKey]: t };
};

/** 下载列模板（输入 / 理想回答 / 元数据），含一行示例 */
export const downloadSampleTemplate = async (): Promise<void> => {
  const XLSX = await loadXLSX();
  const ws = XLSX.utils.aoa_to_sheet([
    [...TEMPLATE_HEADERS],
    ['什么是 RAG？', '检索增强生成', '{"难度":"easy"}'],
    ['什么是向量数据库？', '存储和检索高维向量的数据库', ''],
  ]);
  ws['!cols'] = [{ wch: 32 }, { wch: 40 }, { wch: 24 }];
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, '样本');
  XLSX.writeFile(wb, '评测样本模板.xlsx');
};

/** 解析上传的 Excel/CSV → BulkImportItem[]（走现有 /bulk-import） */
export const parseSpreadsheet = async (
  file: File,
): Promise<BulkImportItem[]> => {
  const XLSX = await loadXLSX();
  const buf = await file.arrayBuffer();
  const wb = XLSX.read(buf, { type: 'array' });
  const sheet = wb.Sheets[wb.SheetNames[0]];
  if (!sheet) return [];
  const rows = XLSX.utils.sheet_to_json<Record<string, unknown>>(sheet, {
    defval: '',
  });

  const pick = (row: Record<string, unknown>, keys: string[]): string => {
    for (const k of keys) {
      if (k in row && row[k] != null && String(row[k]).trim()) {
        return String(row[k]).trim();
      }
    }
    return '';
  };

  const items: BulkImportItem[] = [];
  for (const row of rows) {
    const input = pick(row, ['输入', 'input', 'input_payload', 'question', 'q']);
    const expected = pick(row, ['理想回答', 'expected', 'expected_output', 'answer']);
    const meta = pick(row, ['元数据(JSON)', '元数据(JSON,可选)', '元数据', 'meta']);
    const ip = parseCell(input, 'user_input');
    if (!ip) continue; // 跳过空行
    items.push({
      input_payload: ip,
      expected_output: parseCell(expected, 'answer'),
      meta: parseCell(meta, 'value'),
    });
  }
  return items;
};

/** 当前样本导出为 Excel/CSV 文件 */
export const exportItems = async (
  datasetName: string,
  items: DatasetItemRow[],
  format: 'xlsx' | 'csv' = 'xlsx',
): Promise<void> => {
  const XLSX = await loadXLSX();
  const aoa: (string | number)[][] = [[...TEMPLATE_HEADERS]];
  for (const it of items) {
    aoa.push([
      cellOf(it.input_payload, ['user_input', 'query', 'question', 'input', 'text']),
      cellOf(it.expected_output, ['answer', 'output', 'text']),
      it.meta ? JSON.stringify(it.meta) : '',
    ]);
  }
  const ws = XLSX.utils.aoa_to_sheet(aoa);
  ws['!cols'] = [{ wch: 32 }, { wch: 40 }, { wch: 24 }];
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, '样本');
  const safe = datasetName.replace(/[\\/:*?"<>|]/g, '_') || '评测样本';
  XLSX.writeFile(wb, `${safe}.${format}`);
};
