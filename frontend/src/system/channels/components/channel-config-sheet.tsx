/** Channel 配置抽屉 —— 创建 / 编辑共用，右侧滑入，与模型/供应商配置同一交互范式。
 *
 * 创建：initial=null，必选 provider；编辑：initial=ChannelItem，provider 锁定。
 * api_key 留空不改、空字符串清空、新值覆盖（仅 keyTouched 才提交该字段）。
 */

import { useEffect, useState } from 'react';

import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/core/components/ui/sheet';
import type { EntityId } from '@/core/types/api';
import type {
  ChannelItem,
  ChannelStatus,
  CreateChannelRequest,
  UpdateChannelRequest,
} from '@/system/channels/types/channel';
import type { ProviderItem } from '@/system/providers/types/provider';

interface Props {
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

const Field = ({
  label,
  hint,
  children,
}: {
  label: React.ReactNode;
  hint?: string;
  children: React.ReactNode;
}) => (
  <div className="space-y-1.5">
    <label className="text-[12px] font-medium text-stone-700">{label}</label>
    {children}
    {hint && <p className="text-[10.5px] leading-snug text-stone-500">{hint}</p>}
  </div>
);

export const ChannelConfigSheet = ({
  open,
  initial,
  providers,
  loading,
  onClose,
  onSubmitCreate,
  onSubmitUpdate,
}: Props) => {
  const isEdit = !!initial;
  const [providerId, setProviderId] = useState('');
  const [name, setName] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [keyTouched, setKeyTouched] = useState(false);
  const [baseUrl, setBaseUrl] = useState('');
  const [weight, setWeight] = useState('0');
  const [priority, setPriority] = useState('0');
  const [status, setStatus] = useState<ChannelStatus>('enabled');

  useEffect(() => {
    if (!open) return;
    setProviderId(initial ? String(initial.provider_id) : '');
    setName(initial?.name ?? '');
    setApiKey('');
    setKeyTouched(false);
    setBaseUrl(initial?.base_url ?? '');
    setWeight(initial ? String(initial.weight) : '0');
    setPriority(initial ? String(initial.priority) : '0');
    setStatus(initial?.status ?? 'enabled');
  }, [open, initial]);

  const canSubmit = !!providerId && !!name.trim() && !loading;

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
    <Sheet open={open} onOpenChange={o => !o && onClose()}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            {isEdit ? (
              <>
                <span className="font-mono text-[15px]">{initial?.name}</span>
                <Badge variant="primary">{initial?.provider_code || '?'}</Badge>
              </>
            ) : (
              '新建 Channel'
            )}
          </SheetTitle>
          <SheetDescription>上游凭证与路由调度配置</SheetDescription>
        </SheetHeader>

        <SheetBody className="space-y-5">
          <Field
            label={
              <>
                所属 Provider {!isEdit && <span className="text-rose-500">*</span>}
              </>
            }
            hint={isEdit ? '创建后不可更改' : undefined}
          >
            {isEdit ? (
              <div className="flex h-9 items-center rounded-md border border-stone-200 bg-stone-50 px-3">
                <Badge variant="primary">{initial?.provider_code || `#${initial?.provider_id}`}</Badge>
              </div>
            ) : (
              <Select value={providerId} onValueChange={setProviderId}>
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
            )}
          </Field>

          <Field
            label={
              <>
                名称 <span className="text-rose-500">*</span>
              </>
            }
            hint="同 provider 下用于区分多 key（如 primary / backup / region-cn）"
          >
            <Input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="primary"
              maxLength={64}
            />
          </Field>

          <Field
            label="API Key"
            hint={
              isEdit
                ? '已配置 · 留空不改，新值覆盖'
                : '可选 · 也可后续在编辑里补'
            }
          >
            <Input
              type="password"
              value={apiKey}
              onChange={e => {
                setApiKey(e.target.value);
                setKeyTouched(true);
              }}
              placeholder={isEdit && initial?.has_api_key ? '••••••••（已配置）' : 'sk-...'}
              className="font-mono"
              autoComplete="new-password"
            />
          </Field>

          <Field label="Base URL 覆盖" hint="留空走 provider 默认地址">
            <Input
              type="url"
              value={baseUrl}
              onChange={e => setBaseUrl(e.target.value)}
              placeholder="https://override.example.com/v1"
              maxLength={512}
              className="font-mono"
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="优先级 priority" hint="越高越优先（同级随机）">
              <Input
                type="number"
                value={priority}
                onChange={e => setPriority(e.target.value)}
                min={0}
                step={1}
                className="font-mono"
              />
            </Field>
            <Field label="权重 weight" hint="0 = 平均；>0 加权随机">
              <Input
                type="number"
                value={weight}
                onChange={e => setWeight(e.target.value)}
                min={0}
                step={1}
                className="font-mono"
              />
            </Field>
          </div>

          {isEdit && (
            <Field
              label="状态"
              hint={STATUS_OPTIONS.find(o => o.value === status)?.hint}
            >
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
            </Field>
          )}
        </SheetBody>

        <SheetFooter>
          <Button variant="ghost" size="sm" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button variant="primary" size="sm" disabled={!canSubmit} onClick={handleSubmit}>
            {loading ? '保存中…' : isEdit ? '保存修改' : '创建'}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
};
