/** KB Collections tab —— P20.3 PR #54
 *
 * 列出 KB 下的 collections（chunker 类型 + 索引拓扑）+ 添加 + 删除。
 * collection_type 一经写入不可改（后端守卫）—— 改类型 = 新建后重新 ingest。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Layers, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';

import { get, post } from '@/core/lib/request';
import { SectionCard } from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { Label } from '@/core/components/ui/label';
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { cn } from '@/core/lib/cn';
import { confirm } from '@/core/lib/confirm';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';

type CollectionType = 'generic' | 'faq' | 'wiki' | 'api';

interface CollectionItem {
  id: EntityId;
  kb_id: EntityId;
  collection_type: CollectionType;
  name: string;
  indexes: Array<{ name: string; dim: number; enabled: boolean }>;
  config: Record<string, unknown> | null;
}

interface CreatePayload {
  name: string;
  collection_type: CollectionType;
}

const TYPE_OPTIONS: Array<{ value: CollectionType; label: string; hint: string }> = [
  { value: 'generic', label: 'Generic（通用文档）', hint: '按 char/token/paragraph 切' },
  { value: 'faq', label: 'FAQ（Q/A 对）', hint: '解析 `## Q:` 段，每对一 chunk' },
  { value: 'wiki', label: 'Wiki（长文 + heading）', hint: '按 # 切 + heading path' },
  { value: 'api', label: 'API（OpenAPI YAML/JSON）', hint: '每 endpoint 一 chunk' },
];

const TYPE_COLOR: Record<CollectionType, string> = {
  generic: 'bg-stone-50 text-stone-700',
  faq: 'bg-sky-50 text-sky-700',
  wiki: 'bg-violet-50 text-violet-700',
  api: 'bg-amber-50 text-amber-700',
};

interface Props {
  kbId: EntityId;
}

export const CollectionsTab: React.FC<Props> = ({ kbId }) => {
  const qc = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);

  const listQ = useQuery({
    queryKey: ['kb-collections', kbId],
    queryFn: () => get<CollectionItem[]>(`/v1/admin/kbs/${kbId}/collections`),
    enabled: !!kbId,
  });

  const createMut = useMutation({
    mutationFn: (p: CreatePayload) =>
      post<CollectionItem>(`/v1/admin/kbs/${kbId}/collections`, p),
    onSuccess: c => {
      toast.success(`已新建 collection ${c.name} (${c.collection_type})`);
      qc.invalidateQueries({ queryKey: ['kb-collections', kbId] });
      setAddOpen(false);
    },
    onError: (e: unknown) => {
      toast.error((e as { message?: string })?.message || '新建失败');
    },
  });

  const delMut = useMutation({
    mutationFn: (id: EntityId) =>
      post<null>(`/v1/admin/kbs/${kbId}/collections/${id}/delete`, {}),
    onSuccess: () => {
      toast.success('已删除 collection');
      qc.invalidateQueries({ queryKey: ['kb-collections', kbId] });
    },
    onError: (e: unknown) => {
      toast.error((e as { message?: string })?.message || '删除失败');
    },
  });

  return (
    <>
      <SectionCard>
        <header className="mb-3 flex items-center justify-between">
          <div>
            <h3 className="flex items-center gap-1.5 text-[13px] font-medium text-stone-900">
              <Layers className="h-3.5 w-3.5 text-stone-500" />
              Collections
            </h3>
            <p className="mt-0.5 text-[11.5px] text-stone-500">
              一个 KB 可挂多个 collection；不同 chunker 类型 + 索引拓扑共存。
              <span className="ml-1 text-rose-600">类型一经写入不可改</span>
              （改 = 新建后重新 ingest）
            </p>
          </div>
          <Button size="sm" onClick={() => setAddOpen(true)}>
            <Plus className="mr-1 h-3 w-3" /> 新建 collection
          </Button>
        </header>

        {listQ.isLoading ? (
          <div className="py-8 text-center text-[12px] text-stone-400">
            加载中…
          </div>
        ) : !listQ.data?.length ? (
          <div className="py-12 text-center text-[12px] text-stone-400">
            还没有 collection；点右上"新建 collection"开始
          </div>
        ) : (
          <table className="w-full text-[12.5px]">
            <thead className="text-[11px] uppercase tracking-wider text-stone-500">
              <tr>
                <th className="px-2 py-1.5 text-left">名称</th>
                <th className="px-2 py-1.5 text-left">类型</th>
                <th className="px-2 py-1.5 text-left">索引拓扑</th>
                <th className="px-2 py-1.5 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {listQ.data.map(c => (
                <tr
                  key={String(c.id)}
                  className="border-t border-stone-200/70"
                >
                  <td className="px-2 py-1.5 text-stone-800">{c.name}</td>
                  <td className="px-2 py-1.5">
                    <Badge
                      variant="outline"
                      className={cn(
                        'text-[10.5px]',
                        TYPE_COLOR[c.collection_type],
                      )}
                    >
                      {c.collection_type}
                    </Badge>
                  </td>
                  <td className="px-2 py-1.5 font-mono text-[11px] text-stone-600">
                    {c.indexes
                      .map(
                        idx =>
                          `${idx.name}${idx.enabled === false ? '(off)' : ''}`,
                      )
                      .join(', ')}
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    <button
                      type="button"
                      title="删除"
                      onClick={async () => {
                        if (
                          await confirm({
                            title: '确认删除？',
                            description: `collection ${c.name} 将被移除；该 collection 下的 chunks 留库但 collection_id 置空。`,
                          })
                        ) {
                          delMut.mutate(c.id);
                        }
                      }}
                      className="rounded p-1 text-stone-400 hover:bg-rose-50 hover:text-rose-600"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </SectionCard>

      <CreateCollectionModal
        open={addOpen}
        loading={createMut.isPending}
        onClose={() => setAddOpen(false)}
        onSubmit={p => createMut.mutate(p)}
      />
    </>
  );
};

// ── 新建 modal ─────────────────────────────────────


interface CreateModalProps {
  open: boolean;
  loading: boolean;
  onClose: () => void;
  onSubmit: (p: CreatePayload) => void;
}

const CreateCollectionModal: React.FC<CreateModalProps> = ({
  open,
  loading,
  onClose,
  onSubmit,
}) => {
  const [name, setName] = useState('');
  const [type, setType] = useState<CollectionType>('generic');

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="md">
        <ModalHeader>
          <ModalTitle>新建 Collection</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-3">
          <div className="rounded-md border border-amber-200/70 bg-amber-50/60 px-3 py-2 text-[11.5px] text-amber-800">
            <span className="font-medium">类型一经写入不可改</span> ——
            选错只能新建一个 collection 再重新上传文档 ingest 一次。
          </div>
          <div className="space-y-1.5">
            <Label>
              名称 <span className="text-rose-500">*</span>
            </Label>
            <Input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="faq-zh / api-docs / wiki-pages …"
              maxLength={64}
            />
          </div>
          <div className="space-y-1.5">
            <Label>类型</Label>
            <Select
              value={type}
              onValueChange={v => setType(v as CollectionType)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TYPE_OPTIONS.map(o => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="text-[10.5px] text-stone-500">
              {TYPE_OPTIONS.find(o => o.value === type)?.hint}
            </div>
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button
            variant="primary"
            disabled={!name.trim() || loading}
            onClick={() =>
              onSubmit({ name: name.trim(), collection_type: type })
            }
          >
            {loading ? '创建中…' : '创建'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};
