/** Ability 创建 Modal —— 选 channel + 填 model_code + 优先级/权重
 *
 * 不做编辑（编辑场景由列表行 inline 控件完成 —— priority/weight/enabled 三项）；
 * 删除走 ConfirmDialog；创建后追加到列表。
 */

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
import type { EntityId } from '@/core/types/api';
import type { ChannelItem } from '@/system/channels/types/channel';
import type { CreateAbilityRequest } from '@/system/abilities/types/ability';

interface AbilityFormModalProps {
  open: boolean;
  channels: ChannelItem[];
  loading: boolean;
  onClose: () => void;
  onSubmit: (req: CreateAbilityRequest) => void;
}

export const AbilityFormModal: React.FC<AbilityFormModalProps> = ({
  open,
  channels,
  loading,
  onClose,
  onSubmit,
}) => {
  const [modelCode, setModelCode] = useState('');
  const [channelId, setChannelId] = useState<string>('');
  const [priority, setPriority] = useState('0');
  const [weight, setWeight] = useState('0');
  const [groupId, setGroupId] = useState('');

  useEffect(() => {
    if (open) {
      setModelCode('');
      setChannelId('');
      setPriority('0');
      setWeight('0');
      setGroupId('');
    }
  }, [open]);

  const canSubmit = !!modelCode && !!channelId && !loading;

  const handle = () => {
    if (!canSubmit) return;
    const gid = groupId.trim() ? Number(groupId) : null;
    onSubmit({
      model_code: modelCode.trim(),
      channel_id: channelId as EntityId,
      priority: Number(priority) || 0,
      weight: Number(weight) || 0,
      group_id: gid && Number.isFinite(gid) ? gid : null,
    });
  };

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="md">
        <ModalHeader>
          <ModalTitle>新建 Ability（路由规则）</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          <div className="space-y-1.5">
            <Label>
              Model Code <span className="text-rose-500">*</span>
              <span className="ml-1 text-[11px] text-stone-400">
                · agent 声明的能力名（如 gpt-4 / qwen-plus）
              </span>
            </Label>
            <Input
              value={modelCode}
              onChange={e => setModelCode(e.target.value)}
              placeholder="gpt-4 / qwen-plus / claude-3-opus"
              maxLength={64}
            />
          </div>

          <div className="space-y-1.5">
            <Label>
              路由到 Channel <span className="text-rose-500">*</span>
            </Label>
            <Select value={channelId} onValueChange={setChannelId}>
              <SelectTrigger>
                <SelectValue placeholder="选择 channel…" />
              </SelectTrigger>
              <SelectContent>
                {channels
                  .filter(c => c.status !== 'manual_disabled')
                  .map(c => (
                    <SelectItem key={c.id} value={String(c.id)}>
                      {c.provider_code} · {c.name}
                      {c.status === 'auto_disabled' ? '（已自动停用）' : ''}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>优先级 priority</Label>
              <Input
                type="number"
                value={priority}
                onChange={e => setPriority(e.target.value)}
                min={0}
                step={1}
              />
              <div className="text-[10.5px] text-stone-400">
                越高越优先；同优先级走 weight 加权
              </div>
            </div>
            <div className="space-y-1.5">
              <Label>权重 weight</Label>
              <Input
                type="number"
                value={weight}
                onChange={e => setWeight(e.target.value)}
                min={0}
                step={1}
              />
              <div className="text-[10.5px] text-stone-400">
                0 = 等权随机；&gt;0 加权
              </div>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>
              Group ID
              <span className="ml-1 text-[11px] text-stone-400">
                · 留空 = 全局生效；填数字 = 仅该 group 路由
              </span>
            </Label>
            <Input
              type="number"
              value={groupId}
              onChange={e => setGroupId(e.target.value)}
              placeholder="留空 → 全局"
              min={1}
            />
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button variant="primary" disabled={!canSubmit} onClick={handle}>
            {loading ? '创建中…' : '创建'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};
