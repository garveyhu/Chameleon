/** 注册新 marketplace —— URL + 友好名 */

import { useEffect, useState } from 'react';

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
import type { AddRegistryPayload } from '@/system/marketplace/types/marketplace';

interface Props {
  open: boolean;
  loading: boolean;
  onClose: () => void;
  onSubmit: (p: AddRegistryPayload) => void;
}

export const AddRegistryModal: React.FC<Props> = ({
  open,
  loading,
  onClose,
  onSubmit,
}) => {
  const [url, setUrl] = useState('');
  const [name, setName] = useState('');

  useEffect(() => {
    if (open) {
      setUrl('');
      setName('');
    }
  }, [open]);

  const canSubmit =
    url.trim().length > 0 && name.trim().length > 0 && !loading;

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="md">
        <ModalHeader>
          <ModalTitle>添加 Plugin Marketplace</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-3">
          <div className="rounded-md border border-amber-200/70 bg-amber-50/60 px-3 py-2 text-[11.5px] text-amber-800">
            registry 提供 <span className="font-mono">index.json</span>，
            列已发布的 plugin manifest URL + Ed25519 公钥 pinning。
            添加后点同步即可浏览 / 安装。
          </div>
          <div className="space-y-1.5">
            <Label>
              Registry URL <span className="text-rose-500">*</span>
              <span className="ml-1 text-[11px] text-stone-400">
                · 不带 /index.json
              </span>
            </Label>
            <Input
              value={url}
              onChange={e => setUrl(e.target.value)}
              placeholder="https://registry.chameleon.dev"
              className="font-mono text-[11.5px]"
              maxLength={256}
            />
          </div>
          <div className="space-y-1.5">
            <Label>
              显示名 <span className="text-rose-500">*</span>
            </Label>
            <Input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Chameleon Official"
              maxLength={128}
            />
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button
            variant="primary"
            disabled={!canSubmit}
            onClick={() =>
              onSubmit({
                registry_url: url.trim(),
                name: name.trim(),
              })
            }
          >
            {loading ? '添加中…' : '添加'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};
