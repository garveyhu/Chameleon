/** 知识库列表 —— Dify 式卡片网格 + 创建入口卡 */
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Clock,
  Database,
  FileText,
  ImagePlus,
  Layers,
  MoreVertical,
  Pencil,
  Plus,
  Trash2,
  X,
} from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/core/components/ui/dropdown-menu';
import { Input } from '@/core/components/ui/input';
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import { Textarea } from '@/core/components/ui/textarea';
import { confirm } from '@/core/lib/confirm';
import { formatRelativeReadable } from '@/core/lib/format';
import { fileToIconDataUrl } from '@/core/lib/image';
import { toast } from '@/core/lib/toast';
import { documentApi } from '@/system/kbs/services/document';
import { kbApi } from '@/system/kbs/services/kb';
import type { KbItem } from '@/system/kbs/types/kb';

export const KbsPage = () => {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [editing, setEditing] = useState<KbItem | null>(null);
  const listQ = useQuery({
    queryKey: ['kbs', 1, 100],
    queryFn: () => kbApi.list({ page: 1, page_size: 100 }),
  });
  const items = listQ.data?.items ?? [];

  const open = (k: KbItem) => {
    void qc.prefetchQuery({
      queryKey: ['kb-documents', k.id, 1, 20],
      queryFn: () => documentApi.list(k.id, { page: 1, page_size: 20 }),
    });
    navigate(`/kbs/${k.id}`);
  };

  const deleteMut = useMutation({
    mutationFn: (id: KbItem['id']) => kbApi.delete(id),
    onSuccess: () => {
      toast.success('知识库已删除');
      qc.invalidateQueries({ queryKey: ['kbs'] });
    },
    onError: (e: unknown) => toast.error((e as { message?: string })?.message || '删除失败'),
  });

  const askDelete = async (k: KbItem) => {
    const ok = await confirm({
      title: `删除知识库「${k.name}」？`,
      description: `将永久删除该库的全部数据：${k.document_count} 篇文档、${k.chunk_count} 个切块（含向量）、元数据字段、评测与一致性记录。此操作不可恢复。`,
      confirmText: '永久删除',
      danger: true,
    });
    if (ok) deleteMut.mutate(k.id);
  };

  return (
    <div className="px-1">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {/* 创建入口卡 */}
        <button
          type="button"
          onClick={() => navigate('/kbs/create')}
          className="group flex h-[132px] flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-stone-300 bg-white/60 text-stone-500 transition hover:border-blue-400 hover:bg-blue-50/40 hover:text-blue-600"
        >
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-stone-100 transition group-hover:bg-blue-100">
            <Plus className="h-5 w-5" strokeWidth={1.75} />
          </div>
          <span className="text-[13px] font-medium">创建知识库</span>
          <span className="text-[11px] text-stone-400">导入文档，自动分段 + 向量化</span>
        </button>

        {/* 知识库卡片 */}
        {items.map(k => (
          <div
            key={k.id}
            role="button"
            tabIndex={0}
            onClick={() => open(k)}
            onKeyDown={e => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                open(k);
              }
            }}
            className="group relative flex h-[132px] cursor-pointer flex-col rounded-xl border border-stone-200/80 bg-white p-4 text-left shadow-sm transition hover:border-stone-300 hover:shadow-md"
          >
            {/* 悬浮三点菜单 */}
            <div
              className="absolute right-2 top-2 opacity-0 transition group-hover:opacity-100 data-[open=true]:opacity-100"
              onClick={e => e.stopPropagation()}
            >
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    aria-label="更多操作"
                    className="flex h-7 w-7 items-center justify-center rounded-md text-stone-400 hover:bg-stone-100 hover:text-stone-700"
                  >
                    <MoreVertical className="h-4 w-4" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  align="end"
                  sideOffset={6}
                  className="w-32 rounded-xl border-stone-200/70 p-1 shadow-lg"
                >
                  <DropdownMenuItem
                    onSelect={() => setEditing(k)}
                    className="gap-2 rounded-lg px-2.5 py-1.5 text-[12.5px] text-stone-700"
                  >
                    <Pencil className="h-3.5 w-3.5 text-stone-400" />
                    编辑
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onSelect={() => askDelete(k)}
                    className="gap-2 rounded-lg px-2.5 py-1.5 text-[12.5px] text-rose-600 focus:bg-rose-50 focus:text-rose-700"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    删除
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-emerald-50 text-emerald-600">
                {k.icon ? (
                  <img src={k.icon} alt="" className="h-full w-full object-cover" />
                ) : (
                  <Database className="h-5 w-5" strokeWidth={1.75} />
                )}
              </div>
              <div className="min-w-0 flex-1 pr-7">
                <div className="truncate text-[13.5px] font-medium text-stone-900">{k.name}</div>
                <div className="truncate font-mono text-[10.5px] text-stone-400">{k.kb_key}</div>
              </div>
            </div>
            <p className="mt-2 line-clamp-2 flex-1 text-[11.5px] leading-relaxed text-stone-500">
              {k.description || '暂无描述'}
            </p>
            <div className="mt-auto flex items-center gap-3 text-[11px] text-stone-400">
              <span className="inline-flex items-center gap-1">
                <FileText className="h-3 w-3" />
                {k.document_count} 文档
              </span>
              <span className="inline-flex items-center gap-1">
                <Layers className="h-3 w-3" />
                {k.chunk_count} 切块
              </span>
              <span className="ml-auto inline-flex items-center gap-1 truncate">
                <Clock className="h-3 w-3" />
                更新于 {formatRelativeReadable(k.updated_at)}
              </span>
            </div>
          </div>
        ))}

        {/* 加载骨架 */}
        {listQ.isLoading &&
          items.length === 0 &&
          Array.from({ length: 3 }).map((_, i) => (
            <div key={`skl-${i}`} className="skeleton h-[132px] rounded-xl opacity-60" />
          ))}
      </div>

      <EditKbModal kb={editing} onClose={() => setEditing(null)} />
    </div>
  );
};

const EditKbModal = ({ kb, onClose }: { kb: KbItem | null; onClose: () => void }) => {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [icon, setIcon] = useState<string>('');

  // kb 变化时同步初值（合法的 reset-on-prop-change）
  const [lastId, setLastId] = useState<KbItem['id'] | null>(null);
  if (kb && kb.id !== lastId) {
    setLastId(kb.id);
    setName(kb.name);
    setDescription(kb.description ?? '');
    setIcon(kb.icon ?? '');
  }

  const pickFile = async (file: File) => {
    if (!file.type.startsWith('image/')) {
      toast.error('请选择图片文件');
      return;
    }
    if (file.size > 4 * 1024 * 1024) {
      toast.error('图片过大，请选 4MB 以内');
      return;
    }
    try {
      setIcon(await fileToIconDataUrl(file));
    } catch {
      toast.error('图片读取失败');
    }
  };

  const saveMut = useMutation({
    mutationFn: () => {
      if (!kb) throw new Error('no kb');
      // icon 传空串 = 清除（后端 update_kb 支持）
      return kbApi.update(kb.id, {
        name: name.trim(),
        description: description.trim(),
        icon: icon === (kb.icon ?? '') ? undefined : icon,
      });
    },
    onSuccess: () => {
      toast.success('已保存');
      qc.invalidateQueries({ queryKey: ['kbs'] });
      if (kb) qc.invalidateQueries({ queryKey: ['kb', kb.id] });
      onClose();
    },
  });

  return (
    <Modal open={!!kb} onOpenChange={o => !o && onClose()}>
      <ModalContent size="md">
        <ModalHeader>
          <ModalTitle>编辑知识库</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-3">
          <div>
            <label className="mb-1 block text-[12px] text-stone-600">图标</label>
            <div className="flex items-center gap-3">
              <div className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-emerald-50 text-emerald-600">
                {icon ? (
                  <img src={icon} alt="" className="h-full w-full object-cover" />
                ) : (
                  <Database className="h-6 w-6" strokeWidth={1.6} />
                )}
              </div>
              <div className="flex flex-col gap-1.5">
                <Button
                  variant="ghost"
                  size="sm"
                  type="button"
                  onClick={() => fileRef.current?.click()}
                >
                  <ImagePlus className="mr-1.5 h-3.5 w-3.5" />
                  上传图片
                </Button>
                {icon && (
                  <button
                    type="button"
                    onClick={() => setIcon('')}
                    className="inline-flex items-center gap-1 text-[11px] text-stone-400 hover:text-rose-600"
                  >
                    <X className="h-3 w-3" />
                    移除，用默认图标
                  </button>
                )}
              </div>
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                hidden
                onChange={e => {
                  const f = e.target.files?.[0];
                  if (f) pickFile(f);
                  e.target.value = '';
                }}
              />
            </div>
            <p className="mt-1 text-[10.5px] text-stone-400">自动裁剪缩放为 128×128 小图</p>
          </div>
          <div>
            <label className="mb-1 block text-[12px] text-stone-600">名称</label>
            <Input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="知识库名称"
              className="h-8 text-[12.5px]"
            />
          </div>
          <div>
            <label className="mb-1 block text-[12px] text-stone-600">描述</label>
            <Textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              rows={3}
              placeholder="一句话说明这个知识库装的是什么"
            />
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button onClick={() => saveMut.mutate()} disabled={!name.trim() || saveMut.isPending}>
            {saveMut.isPending ? '保存中…' : '保存'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};
