/** Channel 创建 / 编辑共用 Modal
 *
 * 创建：传 initial=null，必选 provider；提交后调用 onSubmitCreate
 * 编辑：传 initial=ChannelItem，provider 锁定不可改；提交后调用 onSubmitUpdate
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
import type { ProviderItem } from '@/system/providers/types/provider';
import type {
  ChannelItem,
  ChannelStatus,
  CreateChannelRequest,
  UpdateChannelRequest,
} from '@/system/channels/types/channel';

interface ChannelFormModalProps {
  open: boolean;
  /** 编辑模式：传入现有 channel；创建模式：null */
  initial: ChannelItem | null;
  providers: ProviderItem[];
  loading: boolean;
  onClose: () => void;
  onSubmitCreate: (req: CreateChannelRequest) => void;
  onSubmitUpdate: (id: EntityId, req: UpdateChannelRequest) => void;
}

const STATUS_OPTIONS: { value: ChannelStatus; label: string; hint: string }[] = [
  { value: 'enabled', label: '启用', hint: '正常参与路由' },
  { value: 'manual_disabled', label: '手动停用', hint: '管理员人工停用' },
  { value: 'auto_disabled', label: '自动停用', hint: '失败过多被监控降级（一般不直接选）' },
];

export const ChannelFormModal: React.FC<ChannelFormModalProps> = ({
  open,
  initial,
  providers,
  loading,
  onClose,
  onSubmitCreate,
  onSubmitUpdate,
}) => {
  const isEdit = !!initial;
  const [providerId, setProviderId] = useState<string>('');
  const [name, setName] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [keyTouched, setKeyTouched] = useState(false);
  const [baseUrl, setBaseUrl] = useState('');
  const [weight, setWeight] = useState<string>('0');
  const [priority, setPriority] = useState<string>('0');
  const [status, setStatus] = useState<ChannelStatus>('enabled');

  useEffect(() => {
    if (!open) return;
    if (initial) {
      setProviderId(String(initial.provider_id));
      setName(initial.name);
      setApiKey('');
      setKeyTouched(false);
      setBaseUrl(initial.base_url || '');
      setWeight(String(initial.weight));
      setPriority(String(initial.priority));
      setStatus(initial.status);
    } else {
      setProviderId('');
      setName('');
      setApiKey('');
      setKeyTouched(false);
      setBaseUrl('');
      setWeight('0');
      setPriority('0');
      setStatus('enabled');
    }
  }, [open, initial]);

  const canSubmit = !!providerId && !!name && !loading;

  const handleSubmit = () => {
    if (!canSubmit) return;
    const w = Number(weight);
    const p = Number(priority);
    if (isEdit && initial) {
      const req: UpdateChannelRequest = {
        name,
        base_url: baseUrl || undefined,
        status,
        weight: Number.isFinite(w) ? w : undefined,
        priority: Number.isFinite(p) ? p : undefined,
      };
      // 仅 keyTouched 时才提交 api_key 字段（避免误覆盖）
      if (keyTouched) req.api_key = apiKey;
      onSubmitUpdate(initial.id, req);
    } else {
      onSubmitCreate({
        provider_id: providerId,
        name,
        api_key: apiKey || undefined,
        base_url: baseUrl || undefined,
        weight: Number.isFinite(w) ? w : undefined,
        priority: Number.isFinite(p) ? p : undefined,
      });
    }
  };

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="md">
        <ModalHeader>
          <ModalTitle>
            {isEdit ? `编辑 Channel · ${initial?.name}` : '新建 Channel'}
          </ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          <div className="space-y-1.5">
            <Label>
              所属 Provider{' '}
              {isEdit ? (
                <span className="text-[11px] text-stone-400">· 创建后不可改</span>
              ) : (
                <span className="text-rose-500">*</span>
              )}
            </Label>
            <Select
              value={providerId}
              onValueChange={setProviderId}
              disabled={isEdit}
            >
              <SelectTrigger>
                <SelectValue placeholder="选择 provider…" />
              </SelectTrigger>
              <SelectContent>
                {providers.map(p => (
                  <SelectItem key={p.id} value={String(p.id)}>
                    {p.code} · {p.name} ({p.kind})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label>
              名称 <span className="text-rose-500">*</span>
              <span className="ml-1 text-[11px] text-stone-400">
                · 同 provider 下用于区分多 key
              </span>
            </Label>
            <Input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="primary / backup / region-cn"
              maxLength={64}
            />
          </div>

          <div className="space-y-1.5">
            <Label>
              API Key{' '}
              {isEdit ? (
                <span className="text-[11px] text-stone-400">
                  · 已配置；留空不改，空字符串清空，新值覆盖
                </span>
              ) : (
                <span className="text-[11px] text-stone-400">· 可选</span>
              )}
            </Label>
            <Input
              type="password"
              value={apiKey}
              onChange={e => {
                setApiKey(e.target.value);
                setKeyTouched(true);
              }}
              placeholder={
                isEdit && initial?.has_api_key
                  ? '*** 已配置（留空保持不变）'
                  : 'sk-...'
              }
              autoComplete="new-password"
            />
          </div>

          <div className="space-y-1.5">
            <Label>
              Base URL 覆盖
              <span className="ml-1 text-[11px] text-stone-400">
                · 可选，留空走 provider.base_url
              </span>
            </Label>
            <Input
              type="url"
              value={baseUrl}
              onChange={e => setBaseUrl(e.target.value)}
              placeholder="https://override.example.com/v1"
              maxLength={512}
            />
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
                越高越优先（同优先级随机）
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
                0 = 平均；&gt;0 加权随机
              </div>
            </div>
          </div>

          {isEdit && (
            <div className="space-y-1.5">
              <Label>状态</Label>
              <Select value={status} onValueChange={v => setStatus(v as ChannelStatus)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUS_OPTIONS.map(o => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className="text-[10.5px] text-stone-400">
                {STATUS_OPTIONS.find(o => o.value === status)?.hint}
              </div>
            </div>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button variant="primary" disabled={!canSubmit} onClick={handleSubmit}>
            {loading ? '保存中…' : isEdit ? '保存修改' : '创建'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};
