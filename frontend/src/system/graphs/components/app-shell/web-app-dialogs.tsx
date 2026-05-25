/** Web App 弹窗 —— 嵌入接入（iframe 片段）+ web app 设置（写回 embed_config）
 *
 * 都在编辑器内完成，不跳系统页面。公开聊天页为 /embed/{embed_key}。
 */
import { useState } from 'react';

import { Check, Copy, ExternalLink } from 'lucide-react';

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
import { toast } from '@/core/lib/toast';
import type { WebAppInfo } from '@/system/graphs/types/graph';

const useCopy = () => {
  const [copied, setCopied] = useState(false);
  const copy = (text: string) => {
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      toast.success('已复制');
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return { copied, copy };
};

// ── 嵌入接入 ───────────────────────────────────────────────

export const EmbedModal = ({
  open,
  onClose,
  embedKey,
}: {
  open: boolean;
  onClose: () => void;
  embedKey: string;
}) => {
  const origin = window.location.origin;
  const url = `${origin}/embed/${embedKey}`;
  const iframe = `<iframe
  src="${url}"
  style="width: 100%; height: 100%; min-height: 640px; border: 0;"
  allow="microphone">
</iframe>`;
  const { copy } = useCopy();
  const iframeCopy = useCopy();

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="lg">
        <ModalHeader>
          <ModalTitle>嵌入到网站</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          <div>
            <label className="mb-1 block text-[12px] text-stone-600">公开访问 URL</label>
            <div className="flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded-md border border-stone-200 bg-stone-50 px-2 py-1.5 font-mono text-[12px] text-stone-700">
                {url}
              </code>
              <Button size="sm" variant="outline" onClick={() => copy(url)}>
                <Copy className="mr-1 h-3 w-3" />
                复制
              </Button>
              <Button size="sm" variant="outline" onClick={() => window.open(url, '_blank')}>
                <ExternalLink className="mr-1 h-3 w-3" />
                打开
              </Button>
            </div>
          </div>

          <div>
            <label className="mb-1 block text-[12px] text-stone-600">
              将以下 iframe 嵌入到你网站的目标位置
            </label>
            <div className="group relative">
              <pre className="overflow-x-auto rounded-lg bg-stone-900 px-3.5 py-3 font-mono text-[12px] leading-relaxed text-stone-100">
                {iframe}
              </pre>
              <button
                type="button"
                onClick={() => iframeCopy.copy(iframe)}
                title="复制"
                className="absolute top-2 right-2 rounded p-1 text-stone-400 transition hover:bg-stone-700 hover:text-stone-100"
              >
                {iframeCopy.copied ? (
                  <Check className="h-3.5 w-3.5 text-emerald-400" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
              </button>
            </div>
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose}>
            关闭
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

// ── web app 设置 ───────────────────────────────────────────

export const WebAppSettingsModal = ({
  open,
  onClose,
  info,
  onSave,
  saving,
}: {
  open: boolean;
  onClose: () => void;
  info: WebAppInfo;
  onSave: (payload: {
    name: string;
    description: string;
    ui_config: Record<string, unknown>;
    behavior: Record<string, unknown>;
  }) => void;
  saving: boolean;
}) => {
  const [name, setName] = useState(info.name);
  const [desc, setDesc] = useState(info.description ?? '');
  const [color, setColor] = useState((info.ui_config.primary_color as string) || '#0ea5e9');
  const [placeholder, setPlaceholder] = useState((info.behavior.placeholder as string) || '');

  const submit = () =>
    onSave({
      name: name.trim() || info.name,
      description: desc,
      ui_config: { ...info.ui_config, primary_color: color },
      behavior: { ...info.behavior, placeholder: placeholder || undefined },
    });

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="md">
        <ModalHeader>
          <ModalTitle>Web App 设置</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-3">
          <div>
            <label className="mb-1 block text-[12px] text-stone-600">名称</label>
            <Input value={name} onChange={e => setName(e.target.value)} className="h-8" />
          </div>
          <div>
            <label className="mb-1 block text-[12px] text-stone-600">
              描述（展示在聊天页副标题）
            </label>
            <Textarea
              value={desc}
              onChange={e => setDesc(e.target.value)}
              rows={2}
              className="text-[12.5px]"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-[12px] text-stone-600">主题色</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={color}
                  onChange={e => setColor(e.target.value)}
                  className="h-8 w-10 cursor-pointer rounded border border-stone-200 bg-white"
                />
                <Input
                  value={color}
                  onChange={e => setColor(e.target.value)}
                  className="h-8 flex-1 font-mono text-[12px]"
                />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-[12px] text-stone-600">输入框占位符</label>
              <Input
                value={placeholder}
                onChange={e => setPlaceholder(e.target.value)}
                placeholder="输入消息……"
                className="h-8 text-[12px]"
              />
            </div>
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button onClick={submit} disabled={saving}>
            {saving ? '保存中…' : '保存'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};
