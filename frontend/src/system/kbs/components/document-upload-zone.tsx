/** 文档上传区：拖拽 / 点击 + 从 URL / 粘贴文本 三种入口 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { FileUp, Globe, ScrollText } from 'lucide-react';
import { useRef, useState } from 'react';

import { Button } from '@/core/components/ui/button';
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
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import { documentApi } from '@/system/kbs/services/document';

interface Props {
  kbId: import('@/core/types/api').EntityId;
}

export const DocumentUploadZone = ({ kbId }: Props) => {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [urlOpen, setUrlOpen] = useState(false);
  const [textOpen, setTextOpen] = useState(false);

  const uploadMut = useMutation({
    mutationFn: (files: File[]) => documentApi.upload(kbId, files),
    onSuccess: queued => {
      toast.success(`已上传 ${queued.length} 个文件`);
      qc.invalidateQueries({ queryKey: ['kb-documents', kbId] });
    },
  });

  const handleFiles = (files: FileList | File[] | null) => {
    if (!files) return;
    const arr = Array.from(files);
    if (arr.length === 0) return;
    uploadMut.mutate(arr);
  };

  return (
    <>
      <div
        className={cn(
          'rounded-lg border border-dashed bg-stone-50/40 px-6 py-8 transition',
          drag
            ? 'border-amber-400 bg-amber-50/60'
            : 'border-stone-300 hover:border-stone-400',
        )}
        onDragOver={e => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={e => {
          e.preventDefault();
          setDrag(false);
          handleFiles(e.dataTransfer?.files ?? null);
        }}
      >
        <div className="flex flex-col items-center gap-3 text-center">
          <FileUp className="h-7 w-7 text-stone-400" strokeWidth={1.4} />
          <div className="text-[13px] text-stone-700">
            拖入 PDF / Word / Markdown / CSV / TXT / HTML 文件
            <span className="mx-2 text-stone-300">·</span>
            <button
              type="button"
              className="text-amber-700 hover:underline"
              onClick={() => inputRef.current?.click()}
            >
              点击选择
            </button>
          </div>
          <div className="flex items-center gap-2 pt-1">
            <Button variant="ghost" size="sm" onClick={() => setUrlOpen(true)}>
              <Globe className="mr-1.5 h-3.5 w-3.5" /> 从 URL 导入
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setTextOpen(true)}>
              <ScrollText className="mr-1.5 h-3.5 w-3.5" /> 粘贴文本
            </Button>
          </div>
          {uploadMut.isPending && (
            <div className="pt-1 text-[11.5px] text-stone-500">上传中…</div>
          )}
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          hidden
          accept=".pdf,.docx,.doc,.md,.txt,.csv,.html,.htm"
          onChange={e => handleFiles(e.target.files)}
        />
      </div>

      <UrlImportModal
        open={urlOpen}
        onClose={() => setUrlOpen(false)}
        kbId={kbId}
        onDone={() =>
          qc.invalidateQueries({ queryKey: ['kb-documents', kbId] })
        }
      />
      <TextImportModal
        open={textOpen}
        onClose={() => setTextOpen(false)}
        kbId={kbId}
        onDone={() =>
          qc.invalidateQueries({ queryKey: ['kb-documents', kbId] })
        }
      />
    </>
  );
};

interface ModalProps {
  open: boolean;
  onClose: () => void;
  kbId: import('@/core/types/api').EntityId;
  onDone: () => void;
}

const UrlImportModal = ({ open, onClose, kbId, onDone }: ModalProps) => {
  const [url, setUrl] = useState('');
  const [name, setName] = useState('');
  const mut = useMutation({
    mutationFn: () => documentApi.fromUrl(kbId, url, name || undefined),
    onSuccess: () => {
      toast.success('已加入处理队列');
      setUrl('');
      setName('');
      onDone();
      onClose();
    },
  });
  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="md">
        <ModalHeader>
          <ModalTitle>从 URL 导入</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-3">
          <div>
            <label className="mb-1 block text-[12px] text-stone-600">URL</label>
            <Input
              value={url}
              onChange={e => setUrl(e.target.value)}
              placeholder="https://..."
            />
          </div>
          <div>
            <label className="mb-1 block text-[12px] text-stone-600">
              文档名（可选）
            </label>
            <Input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="留空则用 URL"
            />
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button
            disabled={!url || mut.isPending}
            onClick={() => mut.mutate()}
          >
            导入
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

const TextImportModal = ({ open, onClose, kbId, onDone }: ModalProps) => {
  const [name, setName] = useState('');
  const [content, setContent] = useState('');
  const mut = useMutation({
    mutationFn: () => documentApi.fromText(kbId, name, content),
    onSuccess: () => {
      toast.success('已加入处理队列');
      setName('');
      setContent('');
      onDone();
      onClose();
    },
  });
  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="lg">
        <ModalHeader>
          <ModalTitle>粘贴文本</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-3">
          <div>
            <label className="mb-1 block text-[12px] text-stone-600">文档名</label>
            <Input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="如：客户FAQ"
            />
          </div>
          <div>
            <label className="mb-1 block text-[12px] text-stone-600">内容</label>
            <Textarea
              value={content}
              onChange={e => setContent(e.target.value)}
              rows={12}
              placeholder="直接粘贴…"
            />
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button
            disabled={!name || !content || mut.isPending}
            onClick={() => mut.mutate()}
          >
            导入
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};
