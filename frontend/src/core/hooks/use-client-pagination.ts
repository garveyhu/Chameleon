/** 客户端分页 —— 给「后端返整表、前端切片」的传统列表统一套上跳页分页
 *
 * 用法：
 *   const pg = useClientPagination(filteredRows);
 *   <DataTable rows={pg.rows} ... />
 *   <TablePagination page={pg.page} pageSize={pg.pageSize} total={pg.total}
 *     onPageChange={pg.setPage} onPageSizeChange={pg.setPageSize} />
 *
 * items 变化（如筛选）后若当前页越界，自动夹到最后一页（不抖动、不需 effect）。
 */
import { useMemo, useState } from 'react';

export interface ClientPagination<T> {
  page: number;
  pageSize: number;
  total: number;
  rows: T[];
  setPage: (p: number) => void;
  setPageSize: (s: number) => void;
}

export function useClientPagination<T>(items: T[], initialSize = 20): ClientPagination<T> {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSizeRaw] = useState(initialSize);

  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);

  const rows = useMemo(
    () => items.slice((safePage - 1) * pageSize, safePage * pageSize),
    [items, safePage, pageSize],
  );

  return {
    page: safePage,
    pageSize,
    total,
    rows,
    setPage,
    setPageSize: (s: number) => {
      setPageSizeRaw(s);
      setPage(1);
    },
  };
}
