/** 评测样本电子表格（H2 + Phase D）—— 按 DataTable 视觉语言自建的 editable variant。
 *
 *  动态 {{var}} 输入列（来自 input_payload 顶层 key 并集）+ 固定「理想回答 / 元数据 / 操作」列。
 *  行内编辑单格失焦保存（乐观更新）；复杂值/脱敏行点开 JSON 弹层；底部「+新增行」，行尾删除。
 *  与全字段抽屉 / 批量导入并存，互补不替代。
 *
 *  Phase D（Airtable 化）：
 *   - 表头用 getColumnLabel 走中文映射（user_input→用户输入 / hash→哈希 …），未知 key 优雅兜底。
 *   - 系统列（hash/length/token_count）默认隐藏，「列」菜单可勾回；隐藏态存 localStorage。
 *   - 长值省略后 hover 出 Tooltip 看全 / 点开 Popover 看完整；JSON 走 JsonViewer 语法高亮预览。
 *   - 列宽按分类分层（系统列窄 / 业务文本宽）。 */
import { useMemo, useState } from 'react';

import { Columns3, Eye, EyeOff, Lock, Plus, Trash2 } from 'lucide-react';

import { ConfirmDialog } from '@/core/components/common/confirm-dialog';
import { JsonViewer } from '@/core/components/common/json-viewer';
import { Button } from '@/core/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/core/components/ui/dropdown-menu';
import { JsonEditor } from '@/core/components/ui/json-editor';
import { Popover, PopoverContent, PopoverTrigger } from '@/core/components/ui/popover';
import { Tooltip } from '@/core/components/ui/tooltip';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { useDatasetItemMutations } from '@/system/datasets/hooks/useDatasetItemMutations';
import type { DatasetItemRow } from '@/system/datasets/types/dataset';
import {
  EXPECTED_COL_WIDTH,
  META_COL_WIDTH,
  NOTE_COL_WIDTH,
  defaultHiddenColumns,
  getColumnLabel,
  getColumnWidth,
} from '@/system/datasets/utils/dataset-column-meta';
import {
  type CellKind,
  expectedCell,
  inferVarKeys,
  metaSummary,
  parseJsonObject,
  patchExpected,
  patchVar,
  varCell,
} from '@/system/datasets/utils/dataset-spreadsheet';

// 隐藏列偏好按数据集隔离 —— 不同数据集列结构不同，全局 key 会让 A 集的偏好污染 B 集
// 的默认视图（系统列不再被默认隐藏）。
const hiddenColsStorageKey = (datasetId: EntityId): string =>
  `chm:dataset-sheet:hidden-cols:${datasetId}`;

/** 从 localStorage 读本数据集的隐藏列；解析失败/缺失返回 null（交由调用方走默认值）。 */
const readStoredHidden = (datasetId: EntityId): string[] | null => {
  try {
    const raw = localStorage.getItem(hiddenColsStorageKey(datasetId));
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.every(x => typeof x === 'string')) {
      return parsed as string[];
    }
  } catch {
    /* ignore */
  }
  return null;
};

const writeStoredHidden = (datasetId: EntityId, keys: string[]): void => {
  try {
    localStorage.setItem(hiddenColsStorageKey(datasetId), JSON.stringify(keys));
  } catch {
    /* ignore */
  }
};

interface Props {
  items: DatasetItemRow[];
  datasetId: EntityId;
  loading?: boolean;
  /** A2 多选（与表格视图共用同一份选中态，挂在父页）。 */
  selectedIds?: ReadonlySet<EntityId>;
  onToggle?: (id: EntityId) => void;
  allPageSelected?: boolean;
  onToggleAllPage?: () => void;
}

/** 单格行内文本编辑：惰性初始化 draft，失焦/Enter 提交，Esc 还原。
 *  非编辑态长值省略 + hover Tooltip 看全文；编辑态用 textarea 可看多行全文。 */
const EditableText = ({
  initial,
  placeholder,
  onCommit,
}: {
  initial: string;
  placeholder?: string;
  onCommit: (next: string) => void;
}) => {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(initial);

  if (!editing) {
    const trigger = (
      <button
        type="button"
        onClick={() => {
          setDraft(initial);
          setEditing(true);
        }}
        className="block w-full truncate text-left text-stone-700 hover:text-stone-900"
      >
        {initial || <span className="text-stone-300">{placeholder ?? '点击编辑'}</span>}
      </button>
    );
    if (!initial) return trigger;
    return (
      <Tooltip content={<span className="block max-w-xs break-words">{initial}</span>} side="top">
        {trigger}
      </Tooltip>
    );
  }

  const commit = () => {
    setEditing(false);
    if (draft !== initial) onCommit(draft);
  };

  return (
    <textarea
      autoFocus
      rows={Math.min(6, Math.max(1, draft.split('\n').length))}
      value={draft}
      onChange={e => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={e => {
        // Enter 提交、Shift+Enter 换行、Esc 还原
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          (e.target as HTMLTextAreaElement).blur();
        }
        if (e.key === 'Escape') {
          setDraft(initial);
          setEditing(false);
        }
      }}
      className="w-full resize-none rounded border border-blue-300 bg-white px-1.5 py-1 text-[12.5px] leading-snug ring-2 ring-blue-100 outline-none"
    />
  );
};

/** 复杂值（对象/数组/meta）单元格：折叠摘要直显，点开弹层「预览（语法高亮）+ 编辑」双视图。 */
const JsonCellPopover = ({
  label,
  text,
  onCommit,
}: {
  label: string;
  text: string;
  onCommit: (obj: Record<string, unknown>) => void;
}) => {
  const [open, setOpen] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [draft, setDraft] = useState(text);

  const parsed = useMemo<unknown>(() => {
    try {
      return text ? JSON.parse(text) : {};
    } catch {
      return text;
    }
  }, [text]);

  const save = () => {
    const obj = parseJsonObject(draft);
    if (!obj) {
      toast.error('请输入合法的 JSON 对象');
      return;
    }
    onCommit(obj);
    setOpen(false);
  };

  return (
    <Popover
      open={open}
      onOpenChange={o => {
        if (o) {
          setDraft(text);
          setEditMode(false);
        }
        setOpen(o);
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          className="block w-full truncate text-left font-mono text-[11.5px] text-stone-500 hover:text-stone-800"
          title={text}
        >
          {text ? text.replace(/\s+/g, ' ').slice(0, 60) : '{ }'}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[28rem]">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[11.5px] font-medium text-stone-600">{label}</span>
          <button
            type="button"
            onClick={() => setEditMode(m => !m)}
            className="text-[11px] text-stone-500 hover:text-stone-800"
          >
            {editMode ? '查看' : '编辑'}
          </button>
        </div>
        {editMode ? (
          <>
            <JsonEditor label={label} value={draft} onChange={setDraft} />
            <div className="mt-2 flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
                取消
              </Button>
              <Button size="sm" onClick={save}>
                保存
              </Button>
            </div>
          </>
        ) : (
          <JsonViewer value={parsed} searchable={false} maxHeight="20rem" />
        )}
      </PopoverContent>
    </Popover>
  );
};

/** 渲染一个单元格：按 CellKind 分派 文本编辑 / 只读脱敏 / JSON 弹层。 */
/** 备注单元格：行内可编辑文本，失焦提交（值变了才发请求）。外部值变化由父级 key 重挂。 */
const NoteCell = ({
  value,
  onCommit,
}: {
  value: string;
  onCommit: (next: string) => void;
}) => {
  const [text, setText] = useState(value);
  const commit = () => {
    const next = text.trim();
    if (next !== value.trim()) onCommit(next);
  };
  return (
    <textarea
      value={text}
      onChange={e => setText(e.target.value)}
      onBlur={commit}
      rows={1}
      placeholder="备注…"
      title="说明这条样本用于评测什么"
      className="w-full resize-none rounded border border-transparent bg-transparent px-1 py-0.5 text-[12px] leading-snug text-stone-600 outline-none transition placeholder:text-stone-300 hover:border-stone-200 focus:border-blue-300 focus:bg-white"
    />
  );
};

const Cell = ({
  item,
  cell,
  label,
  onScalar,
  onJson,
}: {
  item: DatasetItemRow;
  cell: CellKind;
  label: string;
  onScalar: (next: string) => void;
  onJson: (obj: Record<string, unknown>) => void;
}) => {
  if (cell.kind === 'redacted') {
    return (
      <Tooltip
        content={<span className="block max-w-xs break-words">采样脱敏，不可直接编辑：{cell.preview}</span>}
        side="top"
      >
        <span className="flex items-center gap-1 truncate text-stone-400">
          <Lock className="h-3 w-3 shrink-0" />
          <span className="truncate">{cell.preview}</span>
        </span>
      </Tooltip>
    );
  }
  if (cell.kind === 'json') {
    return <JsonCellPopover label={label} text={cell.text} onCommit={onJson} />;
  }
  // scalar / empty → 行内文本编辑（key 用 item.id + 当前值，确保跨行/换值 remount）
  const initial = cell.kind === 'scalar' ? cell.value : '';
  return (
    <EditableText
      key={`${item.id}:${initial}`}
      initial={initial}
      placeholder="—"
      onCommit={onScalar}
    />
  );
};

/** 「列」下拉菜单：勾选显示/隐藏动态列（系统列默认隐藏，可勾回）。 */
const ColumnMenu = ({
  columnKeys,
  hidden,
  onToggle,
}: {
  columnKeys: string[];
  hidden: ReadonlySet<string>;
  onToggle: (key: string) => void;
}) => (
  <DropdownMenu>
    <DropdownMenuTrigger asChild>
      <Button size="sm" variant="ghost" className="text-stone-500">
        <Columns3 className="mr-1 h-3.5 w-3.5" />列
        {hidden.size > 0 && (
          <span className="ml-1 rounded bg-stone-200/70 px-1 text-[10px] text-stone-500">
            隐 {hidden.size}
          </span>
        )}
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" className="min-w-[11rem]">
      <DropdownMenuLabel>显示列</DropdownMenuLabel>
      <DropdownMenuSeparator />
      {columnKeys.map(k => {
        const isHidden = hidden.has(k);
        return (
          <button
            key={k}
            type="button"
            onClick={() => onToggle(k)}
            className="flex w-full items-center justify-between gap-2 rounded-sm px-2 py-1.5 text-left text-[12.5px] text-stone-700 hover:bg-stone-100"
          >
            <span className="truncate">{getColumnLabel(k)}</span>
            {isHidden ? (
              <EyeOff className="h-3.5 w-3.5 shrink-0 text-stone-300" />
            ) : (
              <Eye className="h-3.5 w-3.5 shrink-0 text-stone-500" />
            )}
          </button>
        );
      })}
    </DropdownMenuContent>
  </DropdownMenu>
);

export const DatasetSpreadsheet = ({
  items,
  datasetId,
  loading,
  selectedIds,
  onToggle,
  allPageSelected,
  onToggleAllPage,
}: Props) => {
  const { update, create, remove } = useDatasetItemMutations(datasetId);
  const [pendingDelete, setPendingDelete] = useState<EntityId | null>(null);
  const selectable = !!onToggle;

  const varKeys = useMemo(() => inferVarKeys(items), [items]);
  // 空 dataset 给一个默认占位列，让「+新增行」有处落值
  const columnKeys = useMemo(() => (varKeys.length > 0 ? varKeys : ['user_input']), [varKeys]);

  // 隐藏列：优先 localStorage，缺失则按分类默认隐藏系统列（hash/length/token_count）。
  const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(
    () => new Set(readStoredHidden(datasetId) ?? defaultHiddenColumns(columnKeys)),
  );

  const toggleColumn = (key: string) => {
    setHiddenColumns(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      writeStoredHidden(datasetId, [...next]);
      return next;
    });
  };

  // 只渲染未隐藏的动态列（固定尾列「理想回答 / 元数据」始终显示）。
  const visibleKeys = useMemo(
    () => columnKeys.filter(k => !hiddenColumns.has(k)),
    [columnKeys, hiddenColumns],
  );

  const onAddRow = () => {
    const input_payload = Object.fromEntries(columnKeys.map(k => [k, '']));
    create.mutate({ input_payload });
  };

  const tableMinWidth = useMemo(() => {
    const dyn = visibleKeys.reduce((sum, k) => sum + getColumnWidth(k), 0);
    return (
      (selectable ? 36 : 0) +
      dyn +
      EXPECTED_COL_WIDTH +
      META_COL_WIDTH +
      NOTE_COL_WIDTH +
      48
    );
  }, [visibleKeys, selectable]);

  if (loading && items.length === 0) {
    return (
      <div className="rounded-lg border border-stone-200/60 p-8 text-center text-[12.5px] text-stone-400">
        加载中…
      </div>
    );
  }

  const totalCols = visibleKeys.length + 3 + (selectable ? 2 : 1);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-end">
        <ColumnMenu columnKeys={columnKeys} hidden={hiddenColumns} onToggle={toggleColumn} />
      </div>

      <div className="relative overflow-x-auto rounded-lg border border-stone-200/60">
        <table className="w-full table-fixed" style={{ minWidth: tableMinWidth }}>
          <colgroup>
            {selectable && <col style={{ width: 36 }} />}
            {visibleKeys.map(k => (
              <col key={k} style={{ width: getColumnWidth(k) }} />
            ))}
            <col style={{ width: EXPECTED_COL_WIDTH }} />
            <col style={{ width: META_COL_WIDTH }} />
            <col style={{ width: NOTE_COL_WIDTH }} />
            <col style={{ width: 48 }} />
          </colgroup>
          <thead className="border-b border-stone-200/70 bg-[var(--color-warm-2)]/40">
            <tr className="text-[11px] font-medium text-stone-500">
              {selectable && (
                <th className="sticky top-0 px-3 py-2.5 text-left font-medium">
                  <input
                    type="checkbox"
                    aria-label="全选本页"
                    checked={!!allPageSelected}
                    onChange={onToggleAllPage}
                    className="h-3.5 w-3.5 accent-stone-700"
                  />
                </th>
              )}
              {visibleKeys.map(k => {
                const label = getColumnLabel(k);
                return (
                  <th key={k} className="sticky top-0 px-3 py-2.5 text-left font-medium">
                    <Tooltip content={k === label ? '' : k} side="top">
                      <span className="block truncate">{label}</span>
                    </Tooltip>
                  </th>
                );
              })}
              <th className="sticky top-0 px-3 py-2.5 text-left font-medium">
                <span className="block truncate">理想回答</span>
              </th>
              <th className="sticky top-0 px-3 py-2.5 text-left font-medium">
                <span className="block truncate">元数据</span>
              </th>
              <th className="sticky top-0 px-3 py-2.5 text-left font-medium">
                <span className="block truncate">备注</span>
              </th>
              <th className="px-3 py-2.5" />
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100 text-[12.5px]">
            {items.length === 0 ? (
              <tr>
                <td colSpan={totalCols} className="py-8 text-center text-stone-400">
                  暂无样本，点下方「新增行」或右上「手工导入」开始
                </td>
              </tr>
            ) : (
              items.map(item => (
                <tr key={item.id} className="group hover:bg-stone-50">
                  {selectable && (
                    <td className="px-3 py-2 align-top">
                      <input
                        type="checkbox"
                        aria-label="选择该样本"
                        checked={!!selectedIds?.has(item.id)}
                        onChange={() => onToggle?.(item.id)}
                        className="mt-0.5 h-3.5 w-3.5 accent-stone-700"
                      />
                    </td>
                  )}
                  {visibleKeys.map(k => (
                    <td key={k} className="px-3 py-2 align-top">
                      <Cell
                        item={item}
                        cell={varCell(item, k)}
                        label={`输入 · ${getColumnLabel(k)}`}
                        onScalar={next =>
                          update.mutate({
                            itemId: item.id,
                            req: { input_payload: patchVar(item, k, next) },
                          })
                        }
                        onJson={obj =>
                          update.mutate({
                            itemId: item.id,
                            req: { input_payload: { ...item.input_payload, [k]: obj } },
                          })
                        }
                      />
                    </td>
                  ))}
                  <td className="px-3 py-2 align-top">
                    <Cell
                      item={item}
                      cell={expectedCell(item)}
                      label="理想回答"
                      onScalar={next =>
                        update.mutate({
                          itemId: item.id,
                          req: { expected_output: patchExpected(item, next) },
                        })
                      }
                      onJson={obj =>
                        update.mutate({
                          itemId: item.id,
                          req: { expected_output: obj },
                        })
                      }
                    />
                  </td>
                  <td className="px-3 py-2 align-top">
                    <JsonCellPopover
                      label="元数据 meta"
                      text={
                        item.meta && Object.keys(item.meta).length > 0
                          ? JSON.stringify(item.meta, null, 2)
                          : ''
                      }
                      onCommit={obj =>
                        update.mutate({
                          itemId: item.id,
                          req: { meta: obj },
                        })
                      }
                    />
                    {metaSummary(item) && (
                      <span className="mt-0.5 block truncate text-[10.5px] text-stone-400">
                        {metaSummary(item)}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 align-top">
                    <NoteCell
                      key={`${item.id}:${item.note ?? ''}`}
                      value={item.note ?? ''}
                      onCommit={next =>
                        update.mutate({
                          itemId: item.id,
                          req: { note: next },
                        })
                      }
                    />
                  </td>
                  <td className="px-3 py-2 text-right align-top">
                    <button
                      type="button"
                      onClick={() => setPendingDelete(item.id)}
                      title="删除该样本"
                      className={cn(
                        'rounded p-1 text-stone-300 opacity-0 transition',
                        'group-hover:opacity-100 hover:bg-rose-50 hover:text-rose-600',
                      )}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Button size="sm" variant="secondary" disabled={create.isPending} onClick={onAddRow}>
        <Plus className="mr-1 h-3.5 w-3.5" />
        {create.isPending ? '新增中…' : '新增行'}
      </Button>

      <ConfirmDialog
        open={pendingDelete != null}
        title="删除样本"
        description="删除后不可恢复，确认删除这条样本？"
        confirmText="删除"
        variant="danger"
        onConfirm={() => {
          if (pendingDelete != null) remove.mutate(pendingDelete);
          setPendingDelete(null);
        }}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
};
