/** 评测样本电子表格（H2）—— 按 DataTable 视觉语言自建的 editable variant。
 *
 *  动态 {{var}} 输入列（来自 input_payload 顶层 key 并集）+ 固定「理想回答 / 元数据 / 操作」列。
 *  行内编辑单格失焦保存（乐观更新）；复杂值/脱敏行点开 JSON 弹层；底部「+新增行」，行尾删除。
 *  与全字段抽屉 / 批量导入并存，互补不替代。 */
import { useMemo, useState } from 'react';

import { Lock, Plus, Trash2 } from 'lucide-react';

import { ConfirmDialog } from '@/core/components/common/confirm-dialog';
import { Button } from '@/core/components/ui/button';
import { JsonEditor } from '@/core/components/ui/json-editor';
import { Popover, PopoverContent, PopoverTrigger } from '@/core/components/ui/popover';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { useDatasetItemMutations } from '@/system/datasets/hooks/useDatasetItemMutations';
import type { DatasetItemRow } from '@/system/datasets/types/dataset';
import {
  type CellKind,
  EXPECTED_COL,
  META_COL,
  expectedCell,
  inferVarKeys,
  metaSummary,
  parseJsonObject,
  patchExpected,
  patchVar,
  varCell,
} from '@/system/datasets/utils/dataset-spreadsheet';

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

/** 单格行内文本编辑：惰性初始化 draft，失焦/Enter 提交，Esc 还原。 */
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
    return (
      <button
        type="button"
        onClick={() => {
          setDraft(initial);
          setEditing(true);
        }}
        className="block w-full truncate text-left text-stone-700 hover:text-stone-900"
        title={initial || placeholder}
      >
        {initial || <span className="text-stone-300">{placeholder ?? '点击编辑'}</span>}
      </button>
    );
  }

  const commit = () => {
    setEditing(false);
    if (draft !== initial) onCommit(draft);
  };

  return (
    <input
      autoFocus
      value={draft}
      onChange={e => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={e => {
        if (e.key === 'Enter') {
          e.preventDefault();
          (e.target as HTMLInputElement).blur();
        }
        if (e.key === 'Escape') {
          setDraft(initial);
          setEditing(false);
        }
      }}
      className="h-7 w-full rounded border border-blue-300 bg-white px-1.5 text-[12.5px] ring-2 ring-blue-100 outline-none"
    />
  );
};

/** 复杂值（对象/数组/meta）JSON 弹层编辑。 */
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
  const [draft, setDraft] = useState(text);

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
        if (o) setDraft(text);
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
      <PopoverContent align="start" className="w-96">
        <div className="mb-2 text-[11.5px] font-medium text-stone-600">{label}</div>
        <JsonEditor label={label} value={draft} onChange={setDraft} />
        <div className="mt-2 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
            取消
          </Button>
          <Button size="sm" onClick={save}>
            保存
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
};

/** 渲染一个单元格：按 CellKind 分派 文本编辑 / 只读脱敏 / JSON 弹层。 */
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
      <span
        className="flex items-center gap-1 truncate text-stone-400"
        title={`采样脱敏，不可直接编辑：${cell.preview}`}
      >
        <Lock className="h-3 w-3 shrink-0" />
        <span className="truncate">{cell.preview}</span>
      </span>
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

  const onAddRow = () => {
    const input_payload = Object.fromEntries(columnKeys.map(k => [k, '']));
    create.mutate({ input_payload });
  };

  const headers = [
    ...columnKeys.map(k => ({ key: k, label: k })),
    { key: EXPECTED_COL, label: '理想回答' },
    { key: META_COL, label: '元数据' },
  ];

  if (loading && items.length === 0) {
    return (
      <div className="rounded-lg border border-stone-200/60 p-8 text-center text-[12.5px] text-stone-400">
        加载中…
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="relative overflow-x-auto rounded-lg border border-stone-200/60">
        <table className="w-full table-fixed" style={{ minWidth: selectable ? 760 : 720 }}>
          <colgroup>
            {selectable && <col style={{ width: 36 }} />}
            {columnKeys.map(k => (
              <col key={k} style={{ width: 180 }} />
            ))}
            <col style={{ width: 220 }} />
            <col style={{ width: 160 }} />
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
              {headers.map(h => (
                <th key={h.key} className="sticky top-0 px-3 py-2.5 text-left font-medium">
                  <span className="block truncate" title={h.label}>
                    {h.label}
                  </span>
                </th>
              ))}
              <th className="px-3 py-2.5" />
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100 text-[12.5px]">
            {items.length === 0 ? (
              <tr>
                <td
                  colSpan={headers.length + (selectable ? 2 : 1)}
                  className="py-8 text-center text-stone-400"
                >
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
                  {columnKeys.map(k => (
                    <td key={k} className="px-3 py-2 align-top">
                      <Cell
                        item={item}
                        cell={varCell(item, k)}
                        label={`输入 · ${k}`}
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
                  <td className="px-3 py-2 text-right align-top">
                    <button
                      type="button"
                      onClick={() => setPendingDelete(item.id)}
                      title="删除该样本"
                      className="rounded p-1 text-stone-300 opacity-0 transition group-hover:opacity-100 hover:bg-rose-50 hover:text-rose-600"
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
