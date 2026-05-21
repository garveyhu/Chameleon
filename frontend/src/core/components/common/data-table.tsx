/** 通用数据表格（分页 + 自定义列）
 *
 * 使用：
 *   <DataTable
 *     columns={[
 *       { key: 'username', title: '用户名' },
 *       { key: 'created_at', title: '创建时间', render: (row) => formatDateTime(row.created_at) },
 *       { key: 'actions', title: '操作', render: (row) => <ActionButtons row={row} /> },
 *     ]}
 *     data={items}
 *     loading={isLoading}
 *     pagination={{ page, pageSize, total, onPageChange }}
 *   />
 */

import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { ReactNode } from 'react';

import { Spinner } from '@/core/components/common/spinner';
import { Button } from '@/core/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/core/components/ui/table';
import { cn } from '@/core/lib/cn';

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

export function DataTable<T extends Record<string, unknown>>({
  columns,
  data,
  loading,
  empty,
  rowKey = 'id' as keyof T,
  pagination,
}: DataTableProps<T>) {
  const getKey = (row: T, idx: number): string | number => {
    if (typeof rowKey === 'function') return rowKey(row);
    const v = row[rowKey];
    return typeof v === 'string' || typeof v === 'number' ? v : idx;
  };

  return (
    <div className="flex flex-col gap-3">
      <Table>
        <TableHeader>
          <TableRow>
            {columns.map(col => (
              <TableHead
                key={col.key}
                style={col.width ? { width: col.width } : undefined}
                className={cn(
                  col.align === 'center' && 'text-center',
                  col.align === 'right' && 'text-right',
                )}
              >
                {col.title}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading ? (
            <TableRow>
              <TableCell colSpan={columns.length} className="text-center py-12">
                <Spinner size="md" className="mx-auto" />
              </TableCell>
            </TableRow>
          ) : data.length === 0 ? (
            <TableRow>
              <TableCell colSpan={columns.length} className="text-center py-12 text-stone-400">
                {empty || '暂无数据'}
              </TableCell>
            </TableRow>
          ) : (
            data.map((row, idx) => (
              <TableRow key={getKey(row, idx)}>
                {columns.map(col => (
                  <TableCell
                    key={col.key}
                    className={cn(
                      col.align === 'center' && 'text-center',
                      col.align === 'right' && 'text-right',
                    )}
                  >
                    {col.render ? col.render(row, idx) : String(row[col.key] ?? '—')}
                  </TableCell>
                ))}
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>

      {pagination && pagination.total > 0 && (
        <div className="flex items-center justify-between px-1 text-sm text-stone-600">
          <span>
            共 <b>{pagination.total}</b> 条，第 {pagination.page} /{' '}
            {Math.max(1, Math.ceil(pagination.total / pagination.pageSize))} 页
          </span>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={pagination.page <= 1}
              onClick={() => pagination.onPageChange(pagination.page - 1)}
            >
              <ChevronLeft className="h-4 w-4" /> 上一页
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={pagination.page * pagination.pageSize >= pagination.total}
              onClick={() => pagination.onPageChange(pagination.page + 1)}
            >
              下一页 <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
