/** 旧 DataTable —— 兼容层，代理到 core/components/table 的 waveflow 风格组件
 *
 * 业务页可保持原用法 `<DataTable columns=[{key,title,render}] data />`，
 * 同步走 waveflow 视觉。新页推荐直接 `import { DataTable } from '@/core/components/table'`。
 */

import type { ReactNode } from 'react';

import {
  DataTable as WfDataTable,
  type DataTableColumn as WfColumn,
  TablePagination,
} from '@/core/components/table';

export interface DataTableColumn<T> {
  key: string;
  title: string;
  width?: string;
  align?: 'left' | 'center' | 'right';
  render?: (row: T, index: number) => ReactNode;
}

export interface DataTablePagination {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}

interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  data: T[];
  loading?: boolean;
  empty?: ReactNode;
  rowKey?: keyof T | ((row: T) => string | number);
  pagination?: DataTablePagination;
}

export function DataTable<T>({
  columns,
  data,
  loading,
  empty,
  rowKey = 'id' as keyof T,
  pagination,
}: DataTableProps<T>) {
  const wfColumns: WfColumn<T>[] = columns.map(c => ({
    key: c.key,
    header: c.title,
    width: c.width ? Number(c.width.replace(/[^\d]/g, '')) || undefined : undefined,
    align: c.align,
    render: c.render
      ? c.render
      : (row: T) => {
          const v = (row as Record<string, unknown>)[c.key];
          return v === null || v === undefined ? '—' : String(v);
        },
  }));

  return (
    <>
      <WfDataTable
        columns={wfColumns}
        rows={data}
        rowKey={rowKey}
        loading={loading}
        emptyText={empty || '暂无数据'}
      />
      {pagination && pagination.total > 0 && (
        <TablePagination
          page={pagination.page}
          pageSize={pagination.pageSize}
          total={pagination.total}
          onPageChange={pagination.onPageChange}
          onPageSizeChange={() => {
            /* 老 API 不支持改 pageSize；新页迁移到 core/components/table 后启用 */
          }}
        />
      )}
    </>
  );
}
