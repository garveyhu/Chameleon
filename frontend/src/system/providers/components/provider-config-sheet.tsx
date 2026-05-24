/** 供应商配置抽屉 —— 编辑 provider 的 name / base_url / api_key / 描述 / 启用。
 *
 * 原 providers 页只能新建 + 切 enabled，无法编辑配置（用户痛点）。code / kind 是
 * 身份标识不可改，只读展示；api_key 留空表示不修改（不回显明文）。
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/core/components/ui/sheet';
import { Switch } from '@/core/components/ui/switch';
import { Textarea } from '@/core/components/ui/textarea';
import { toast } from '@/core/lib/toast';
import { providerApi } from '@/system/providers/services/provider';
import type { ProviderItem } from '@/system/providers/types/provider';

interface Props {
  provider: ProviderItem | null;
  onClose: () => void;
}

const Field = ({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) => (
  <div className="space-y-1.5">
    <label className="text-[12px] font-medium text-stone-700">{label}</label>
    {children}
    {hint && <p className="text-[10.5px] leading-snug text-stone-500">{hint}</p>}
  </div>
);

export const ProviderConfigSheet = ({ provider, onClose }: Props) => {
  const qc = useQueryClient();
  const [name, setName] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [description, setDescription] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [enabled, setEnabled] = useState(true);

  useEffect(() => {
    if (!provider) return;
    setName(provider.name);
    setBaseUrl(provider.base_url || '');
    setDescription(provider.description || '');
    setApiKey('');
    setEnabled(provider.enabled);
  }, [provider]);

  const saveMut = useMutation({
    mutationFn: () =>
      providerApi.update(provider!.id, {
        name,
        base_url: baseUrl || undefined,
        description: description || undefined,
        api_key: apiKey || undefined,
        enabled,
      }),
    onSuccess: () => {
      toast.success('供应商配置已保存');
      qc.invalidateQueries({ queryKey: ['providers'] });
      onClose();
    },
  });

  return (
    <Sheet open={!!provider} onOpenChange={o => !o && onClose()}>
      <SheetContent>
        {provider && (
          <>
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2">
                <span className="font-mono text-[15px]">{provider.code}</span>
                <Badge variant="primary">{provider.kind}</Badge>
              </SheetTitle>
              <SheetDescription>配置接入凭证与基础地址</SheetDescription>
            </SheetHeader>

            <SheetBody className="space-y-5">
              <Field label="名称">
                <Input value={name} onChange={e => setName(e.target.value)} />
              </Field>
              <Field label="Base URL" hint="留空走 provider 默认地址">
                <Input
                  value={baseUrl}
                  onChange={e => setBaseUrl(e.target.value)}
                  placeholder="https://api.example.com/v1"
                  className="font-mono"
                />
              </Field>
              <Field
                label="API Key"
                hint={
                  provider.has_api_key
                    ? '已配置 · 留空则不修改，填入以替换'
                    : '未配置 · 填入以设置'
                }
              >
                <Input
                  type="password"
                  value={apiKey}
                  onChange={e => setApiKey(e.target.value)}
                  placeholder={provider.has_api_key ? '••••••••（已配置）' : 'sk-...'}
                  className="font-mono"
                />
              </Field>
              <Field label="描述">
                <Textarea
                  rows={2}
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                />
              </Field>

              <div className="flex items-center justify-between rounded-lg border border-stone-200 px-3 py-2.5">
                <div>
                  <div className="text-[12.5px] font-medium text-stone-800">启用</div>
                  <div className="text-[11px] text-stone-500">
                    关闭后该供应商下的模型 / channel 不可用
                  </div>
                </div>
                <Switch checked={enabled} onCheckedChange={setEnabled} />
              </div>
            </SheetBody>

            <SheetFooter>
              <Button variant="ghost" size="sm" onClick={onClose}>
                取消
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => saveMut.mutate()}
                disabled={saveMut.isPending || !name.trim()}
              >
                {saveMut.isPending ? '保存中…' : '保存配置'}
              </Button>
            </SheetFooter>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
};
