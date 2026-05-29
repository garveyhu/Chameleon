/** 会话文件管理页（观测域）
 *
 * 数据源：admin /v1/admin/session-files。分页 + 多条件查询 + 详情抽屉 +
 * 手动删除（级联清 Document/chunks/MinIO）。
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';

import { Eye, FileText, Image as ImageIcon, Music, Sheet, Trash2 } from 'lucide-react';

import { DateRangePicker, type DateRange } from '@/core/components/common/date-range-picker';
import { EmptyState } from '@/core/components/common/empty-state';
import {
  DataTable,
  type DataTableColumn,
  SectionCard,
  TablePagination,
  TableToolbar,
} from '@/core/components/table';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { StatusBadge } from '@/core/components/ui/status-badge';
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import {
  Sheet as DrawerRoot,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/core/components/ui/sheet';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import { FilePreviewModal, type PreviewTarget } from '@/system/session_files/components/file-preview-modal';
import { sessionFileApi } from '@/system/session_files/services/session-file';
import type { SessionFileItem } from '@/system/session_files/types/session-file';

const KIND_OPTIONS = [
  { value: 'image', label: '图片' },
  { value: 'audio', label: '音频' },
  { value: 'document', label: '文档' },
  { value: 'data', label: '数据' },
  { value: 'other', label: '其他' },
];

const STATUS_OPTIONS = [
  { value: 'uploaded', label: '已上传' },
  { value: 'parsing', label: '解析中' },
  { value: 'indexing', label: '建索引' },
  { value: 'ready', label: '就绪' },
  { value: 'failed', label: '失败' },
];

const KIND_LABEL: Record<string, string> = Object.fromEntries(
  KIND_OPTIONS.map(o => [o.value, o.label]),
);

const STATUS_TONE: Record<string, 'neutral' | 'success' | 'warning' | 'error'> = {
  uploaded: 'neutral',
  parsing: 'warning',
  indexing: 'warning',
  ready: 'success',
  failed: 'error',
};

const KindIcon = ({ kind }: { kind: string }) => {
  const cls = 'h-3.5 w-3.5 text-stone-400';
  if (kind === 'image') return <ImageIcon className={cls} />;
  if (kind === 'audio') return <Music className={cls} />;
  if (kind === 'data') return <Sheet className={cls} />;
  return <FileText className={cls} />;
};

const formatSize = (n: number): string => {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
};

/** 默认时间区间：近 7 天（含今天） */
const defaultRange = (): DateRange => {
  const to = new Date();
  to.setHours(23, 59, 59, 999);
  const from = new Date();
  from.setDate(from.getDate() - 6);
  from.setHours(0, 0, 0, 0);
  return { from, to };
};

export const SessionFilesPage = () => {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [sessionId, setSessionId] = useState('');
  const [endUserId, setEndUserId] = useState('');
  const [kind, setKind] = useState('all');
  const [status, setStatus] = useState('all');
  const [filenameKw, setFilenameKw] = useState('');
  const [filenameDraft, setFilenameDraft] = useState('');
  const [range, setRange] = useState<DateRange>(defaultRange);

  const [detail, setDetail] = useState<SessionFileItem | null>(null);
  const [deleting, setDeleting] = useState<SessionFileItem | null>(null);
  const [previewFile, setPreviewFile] = useState<PreviewTarget | null>(null);

  const resetPage = () => setPage(1);

  const sinceIso = range.from.toISOString();
  const untilIso = range.to.toISOString();
  const listQ = useQuery({
    queryKey: [
      'session-files',
      page,
      pageSize,
      sessionId,
      endUserId,
      kind,
      status,
      filenameKw,
      sinceIso,
      untilIso,
    ],
    queryFn: () =>
      sessionFileApi.list({
        page,
        page_size: pageSize,
        session_id: sessionId || undefined,
        end_user_id: endUserId || undefined,
        kind: kind === 'all' ? undefined : kind,
        status: status === 'all' ? undefined : status,
        filename: filenameKw || undefined,
        since: sinceIso,
        until: untilIso,
      }),
    placeholderData: keepPreviousData,
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => sessionFileApi.delete(id),
    onSuccess: () => {
      toast.success('文件已删除');
      setDeleting(null);
      qc.invalidateQueries({ queryKey: ['session-files'] });
    },
    onError: e => toast.error(`删除失败：${(e as Error).message}`),
  });

  const rows = listQ.data?.items ?? [];

  const columns: DataTableColumn<SessionFileItem>[] = [
    {
      key: 'filename',
      header: '文件名',
      render: r => (
        <div className="group/fn flex min-w-0 items-center gap-1.5">
          <KindIcon kind={r.kind} />
          <span className="truncate text-[12.5px]" title={r.filename}>
            {r.filename}
          </span>
          <button
            type="button"
            title="预览"
            onClick={e => {
              e.stopPropagation();
              setPreviewFile({ id: r.id, filename: r.filename, mime: r.mime });
            }}
            className="shrink-0 rounded p-0.5 text-stone-400 opacity-0 transition hover:bg-stone-100 hover:text-blue-600 group-hover/fn:opacity-100"
          >
            <Eye className="h-3.5 w-3.5" />
          </button>
        </div>
      ),
    },
    {
      key: 'kind',
      header: '类型',
      width: 70,
      render: r => (
        <span className="text-[11.5px] text-stone-600">{KIND_LABEL[r.kind] || r.kind}</span>
      ),
    },
    {
      key: 'size',
      header: '大小',
      width: 84,
      align: 'right',
      render: r => (
        <span className="tnum font-mono text-[11.5px] text-stone-600">
          {formatSize(r.size)}
        </span>
      ),
    },
    {
      key: 'status',
      header: '状态',
      width: 80,
      render: r => (
        <StatusBadge tone={STATUS_TONE[r.status] ?? 'default'}>
          {STATUS_OPTIONS.find(s => s.value === r.status)?.label ?? r.status}
        </StatusBadge>
      ),
    },
    {
      key: 'session',
      header: '会话',
      width: 120,
      render: r => (
        <span
          className="truncate font-mono text-[10.5px] text-stone-500"
          title={r.session_id}
        >
          {r.session_id.slice(0, 12)}…
        </span>
      ),
    },
    {
      key: 'end_user',
      header: '终端用户',
      width: 130,
      render: r =>
        r.end_user_id ? (
          <span
            className="truncate font-mono text-[10.5px] text-stone-500"
            title={r.end_user_id}
          >
            {r.end_user_id.length > 16 ? r.end_user_id.slice(0, 16) + '…' : r.end_user_id}
          </span>
        ) : (
          <span className="text-stone-300">—</span>
        ),
    },
    {
      key: 'created',
      header: '上传时间',
      width: 150,
      render: r => (
        <span className="text-[11.5px] text-stone-500">{formatDateTime(r.created_at)}</span>
      ),
    },
    {
      key: 'actions',
      header: '',
      width: 60,
      render: r => (
        <div className="flex items-center justify-end">
          <Button
            size="icon-sm"
            variant="ghost"
            type="button"
            onClick={e => {
              e.stopPropagation();
              setDeleting(r);
            }}
            title="删除"
          >
            <Trash2 className="h-3.5 w-3.5 text-rose-500" />
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <SectionCard>
        <TableToolbar
          title="会话文件"
          onRefresh={() => listQ.refetch()}
          leadingExtra={
            <DateRangePicker
              value={range}
              onChange={v => {
                setRange(v);
                resetPage();
              }}
            />
          }
          search={{
            value: filenameDraft,
            onChange: setFilenameDraft,
            onSubmit: v => {
              setFilenameKw(v);
              resetPage();
            },
            placeholder: '文件名关键字',
            width: 180,
          }}
          filters={[
            {
              value: kind,
              onChange: v => {
                setKind(v);
                resetPage();
              },
              placeholder: '类型',
              options: KIND_OPTIONS,
              width: 110,
            },
            {
              value: status,
              onChange: v => {
                setStatus(v);
                resetPage();
              },
              placeholder: '状态',
              options: STATUS_OPTIONS,
              width: 110,
            },
          ]}
          extra={
            <>
              <Input
                className="!h-7 text-[12px]"
                style={{ width: 168 }}
                placeholder="会话 ID"
                value={sessionId}
                onChange={e => setSessionId(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') resetPage();
                }}
              />
              <Input
                className="!h-7 text-[12px]"
                style={{ width: 168 }}
                placeholder="终端用户 ID"
                value={endUserId}
                onChange={e => setEndUserId(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') resetPage();
                }}
              />
            </>
          }
        />

        <DataTable
          columns={columns}
          rows={rows}
          rowKey="id"
          loading={listQ.isLoading}
          refreshing={listQ.isFetching}
          onRowClick={r => setDetail(r)}
          emptyText={
            <EmptyState
              icon={<FileText strokeWidth={1.5} />}
              title="暂无会话文件"
            />
          }
        />

        <TablePagination
          page={page}
          pageSize={pageSize}
          total={listQ.data?.total || 0}
          onPageChange={setPage}
          onPageSizeChange={s => {
            setPageSize(s);
            resetPage();
          }}
        />
      </SectionCard>

      <DetailDrawer
        file={detail}
        onClose={() => setDetail(null)}
        onPreview={f => setPreviewFile({ id: f.id, filename: f.filename, mime: f.mime })}
      />

      <FilePreviewModal file={previewFile} onClose={() => setPreviewFile(null)} />

      <Modal open={!!deleting} onOpenChange={open => !open && setDeleting(null)}>
        <ModalContent className="!max-w-[440px]">
          <ModalHeader>
            <ModalTitle>删除会话文件</ModalTitle>
          </ModalHeader>
          <ModalBody>
            {deleting ? (
              <div className="space-y-2 text-[13px]">
                <p>
                  确定删除文件 <strong>{deleting.filename}</strong>？
                </p>
                <p className="text-[12px] text-stone-500">
                  同步软删该文件的所有切块；MinIO object 后台异步清理。已发送过的消息引用该文件 URL
                  将仍可见（但内容可能 404）。
                </p>
              </div>
            ) : null}
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" onClick={() => setDeleting(null)}>
              取消
            </Button>
            <Button
              variant="danger"
              loading={deleteMut.isPending}
              onClick={() => deleting && deleteMut.mutate(deleting.id)}
            >
              确认删除
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </div>
  );
};

// ── 详情抽屉 ───────────────────────────────────────────────

const DetailDrawer = ({
  file,
  onClose,
  onPreview,
}: {
  file: SessionFileItem | null;
  onClose: () => void;
  onPreview: (f: SessionFileItem) => void;
}) => {
  const open = !!file;
  const detailQ = useQuery({
    queryKey: ['session-files', 'detail', file?.id],
    queryFn: () => sessionFileApi.get(file!.id),
    enabled: open,
  });
  const f = detailQ.data ?? file;

  return (
    <DrawerRoot open={open} onOpenChange={o => !o && onClose()}>
      <SheetContent side="right" className="!w-[640px] !max-w-[92vw]">
        <SheetHeader>
          <SheetTitle>{f?.filename ?? '会话文件详情'}</SheetTitle>
        </SheetHeader>
        {f ? (
          <SheetBody className="text-[12.5px]">
            <KvBlock
              rows={[
                [
                  '预览',
                  <button
                    key="preview"
                    type="button"
                    onClick={() => onPreview(f)}
                    className="inline-flex items-center gap-1 rounded-md border border-stone-200 bg-white px-2 py-0.5 text-[12px] text-stone-600 transition hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600"
                  >
                    <Eye className="h-3.5 w-3.5" />
                    预览文件
                  </button>,
                ],
                ['ID', String(f.id)],
                ['类型', `${KIND_LABEL[f.kind] || f.kind}（${f.mime}）`],
                ['大小', formatSize(f.size)],
                ['状态', f.status],
                ['会话 ID', f.session_id],
                ['终端用户', f.end_user_id || '—'],
                ['上传时间', formatDateTime(f.created_at)],
                [
                  '解析结果',
                  f.text_size != null
                    ? `${f.text_size.toLocaleString()} 字符 · ${
                        f.use_full_text ? '小文件全文喂' : '大文件切块向量'
                      }`
                    : '—',
                ],
                [
                  '切块数',
                  detailQ.data?.chunk_count != null ? String(detailQ.data.chunk_count) : '—',
                ],
                ['MinIO object_id', f.object_id],
                ...(f.error ? ([['错误', f.error]] as [string, ReactNode][]) : []),
              ]}
            />
          </SheetBody>
        ) : null}
      </SheetContent>
    </DrawerRoot>
  );
};

const KvBlock = ({ rows }: { rows: [string, ReactNode][] }) => (
  <div className="divide-y divide-stone-100 rounded-lg border border-stone-200">
    {rows.map(([k, v]) => (
      <div key={k} className="grid grid-cols-[120px_1fr] items-center gap-2 px-3 py-1.5">
        <div className="text-[11px] text-stone-500">{k}</div>
        <div className="break-all font-mono text-[11.5px] text-stone-800">{v}</div>
      </div>
    ))}
  </div>
);
