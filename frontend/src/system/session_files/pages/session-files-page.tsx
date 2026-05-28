/** 会话文件管理页（观测域）
 *
 * 数据源：admin /v1/admin/session-files。分页 + 多条件查询 + 详情抽屉 +
 * 手动删除（级联清 Document/chunks/MinIO）。
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { FileText, Image as ImageIcon, Music, Sheet, Trash2 } from 'lucide-react';

import { EmptyState } from '@/core/components/common/empty-state';
import {
  DataTable,
  type DataTableColumn,
  SectionCard,
  TablePagination,
  TableToolbar,
} from '@/core/components/table';
import { Button } from '@/core/components/ui/button';
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
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/core/components/ui/sheet';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
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

  const [detail, setDetail] = useState<SessionFileItem | null>(null);
  const [deleting, setDeleting] = useState<SessionFileItem | null>(null);

  const resetPage = () => setPage(1);

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
      }),
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
        <div className="flex min-w-0 items-center gap-1.5">
          <KindIcon kind={r.kind} />
          <span className="truncate text-[12.5px]" title={r.filename}>
            {r.filename}
          </span>
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
        />

        <div className="mb-2 flex flex-wrap items-center gap-1.5">
          <input
            value={sessionId}
            onChange={e => setSessionId(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') resetPage();
            }}
            placeholder="会话 ID 精确匹配"
            className="h-7 w-[260px] rounded border border-stone-200 px-2 font-mono text-[11px]"
          />
          <input
            value={endUserId}
            onChange={e => setEndUserId(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') resetPage();
            }}
            placeholder="终端用户 ID 精确匹配"
            className="h-7 w-[200px] rounded border border-stone-200 px-2 font-mono text-[11px]"
          />
        </div>

        <DataTable
          columns={columns}
          rows={rows}
          rowKey="id"
          loading={listQ.isLoading}
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

      <DetailDrawer file={detail} onClose={() => setDetail(null)} />

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
}: {
  file: SessionFileItem | null;
  onClose: () => void;
}) => {
  const open = !!file;
  const detailQ = useQuery({
    queryKey: ['session-files', 'detail', file?.id],
    queryFn: () => sessionFileApi.get(file!.id),
    enabled: open,
  });
  const previewQ = useQuery({
    queryKey: ['session-files', 'preview', file?.id],
    queryFn: () => sessionFileApi.preview(file!.id),
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
          <div className="space-y-4 px-5 py-3 text-[12.5px]">
            <FilePreview
              filename={f.filename}
              loading={previewQ.isLoading}
              preview={previewQ.data ?? null}
            />
            <KvBlock
              rows={[
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
                  detailQ.data?.chunk_count != null
                    ? String(detailQ.data.chunk_count)
                    : '—',
                ],
                ['MinIO object_id', f.object_id],
                ...(f.error ? ([['错误', f.error]] as [string, string][]) : []),
              ]}
            />
            {previewQ.data?.url ? (
              <div className="flex gap-2">
                <Button asChild variant="outline" size="sm">
                  <a href={previewQ.data.url} download={f.filename}>
                    下载源文件
                  </a>
                </Button>
              </div>
            ) : null}
          </div>
        ) : null}
      </SheetContent>
    </DrawerRoot>
  );
};

const FilePreview = ({
  filename,
  loading,
  preview,
}: {
  filename: string;
  loading: boolean;
  preview: import('@/system/session_files/types/session-file').SessionFilePreview | null;
}) => {
  if (loading) {
    return (
      <div className="rounded-lg border border-dashed border-stone-200 bg-stone-50 px-3 py-6 text-center text-[12px] text-stone-400">
        加载预览中…
      </div>
    );
  }
  if (!preview) {
    return (
      <div className="rounded-lg border border-dashed border-stone-200 bg-stone-50 px-3 py-6 text-center text-[12px] text-stone-400">
        无预览数据
      </div>
    );
  }
  if (preview.note) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-4 text-[12px] text-amber-700">
        {preview.note}
      </div>
    );
  }

  if (preview.kind === 'image' && preview.url) {
    return (
      <div className="overflow-hidden rounded-lg border border-stone-200">
        <img
          src={preview.url}
          alt=""
          className="max-h-[360px] w-full bg-stone-50 object-contain"
        />
      </div>
    );
  }
  if (preview.kind === 'pdf' && preview.url) {
    return (
      <iframe
        title={filename}
        src={preview.url}
        className="h-[420px] w-full rounded-lg border border-stone-200"
      />
    );
  }
  if (preview.kind === 'audio' && preview.url) {
    return <audio controls src={preview.url} className="w-full" />;
  }
  if ((preview.kind === 'text' || preview.kind === 'office') && preview.text != null) {
    return (
      <div className="overflow-hidden rounded-lg border border-stone-200 bg-stone-50">
        <div className="border-b border-stone-200 bg-white px-3 py-1.5 text-[11px] text-stone-500">
          {preview.kind === 'office' ? '已抽取为纯文本' : '文本预览'}
          {preview.truncated ? '（已截断）' : ''}
        </div>
        <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap break-words p-3 font-mono text-[11.5px] leading-relaxed text-stone-800">
          {preview.text}
        </pre>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-dashed border-stone-200 bg-stone-50 px-3 py-6 text-center text-[12px] text-stone-500">
      该类型不支持内嵌预览，请使用下方按钮下载查看
    </div>
  );
};

const KvBlock = ({ rows }: { rows: [string, string][] }) => (
  <div className="divide-y divide-stone-100 rounded-lg border border-stone-200">
    {rows.map(([k, v]) => (
      <div key={k} className="grid grid-cols-[120px_1fr] gap-2 px-3 py-1.5">
        <div className="text-[11px] text-stone-500">{k}</div>
        <div className="break-all font-mono text-[11.5px] text-stone-800">{v}</div>
      </div>
    ))}
  </div>
);
