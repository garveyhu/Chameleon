/** 新建 workspace modal */

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import type {
  CreateWorkspacePayload,
  WorkspacePlan,
} from '@/system/workspaces/types/workspace';
import { PLAN_OPTIONS } from '@/system/workspaces/types/workspace';

interface Props {
  open: boolean;
  loading: boolean;
  onClose: () => void;
  onSubmit: (p: CreateWorkspacePayload) => void;
}

export const CreateWorkspaceModal: React.FC<Props> = ({
  open,
  loading,
  onClose,
  onSubmit,
}) => {
  const [key, setKey] = useState('');
  const [name, setName] = useState('');
  const [plan, setPlan] = useState<WorkspacePlan>('free');

  useEffect(() => {
    if (open) {
      setKey('');
      setName('');
      setPlan('free');
    }
  }, [open]);

  const canSubmit =
    !loading && /^[a-zA-Z][a-zA-Z0-9_\-]{0,63}$/.test(key) && name.trim();

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="md">
        <ModalHeader>
          <ModalTitle>新建 workspace</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-3">
          <div className="space-y-1.5">
            <Label>
              workspace_key <span className="text-rose-500">*</span>
              <span className="ml-1 text-[11px] text-stone-400">
                · 唯一；字母开头，a-zA-Z0-9_-
              </span>
            </Label>
            <Input
              value={key}
              onChange={e => setKey(e.target.value)}
              placeholder="acme-corp"
              className="font-mono"
              maxLength={64}
            />
          </div>
          <div className="space-y-1.5">
            <Label>
              显示名 <span className="text-rose-500">*</span>
            </Label>
            <Input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Acme 工作区"
              maxLength={128}
            />
          </div>
          <div className="space-y-1.5">
            <Label>套餐</Label>
            <Select
              value={plan}
              onValueChange={v => setPlan(v as WorkspacePlan)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PLAN_OPTIONS.map(o => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
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
                workspace_key: key.trim(),
                name: name.trim(),
                plan,
              })
            }
          >
            {loading ? '创建中…' : '创建'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};
