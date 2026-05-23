/** Plugin config 编辑 Modal —— JSON textarea；下一版接 JsonSchemaForm 渲染 config_schema */

import { useEffect, useMemo, useState } from 'react';

import { Button } from '@/core/components/ui/button';
import { Label } from '@/core/components/ui/label';
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import type { PluginInstanceItem } from '@/system/plugins/types/plugin';

interface PluginConfigModalProps {
  open: boolean;
  plugin: PluginInstanceItem | null;
  loading: boolean;
  onClose: () => void;
  onSubmit: (config: Record<string, unknown>) => void;
}

export const PluginConfigModal: React.FC<PluginConfigModalProps> = ({
  open,
  plugin,
  loading,
  onClose,
  onSubmit,
}) => {
  const [text, setText] = useState('{}');

  useEffect(() => {
    if (open && plugin) {
      setText(JSON.stringify(plugin.config ?? {}, null, 2));
    }
  }, [open, plugin]);

  const parsed = useMemo(() => {
    try {
      const obj = JSON.parse(text);
      if (typeof obj !== 'object' || Array.isArray(obj) || obj === null) {
        return { ok: false as const, error: 'config 必须是 JSON 对象 {}' };
      }
      return { ok: true as const, obj };
    } catch (e) {
      return { ok: false as const, error: `JSON 解析失败: ${(e as Error).message}` };
    }
  }, [text]);

  const handleSubmit = () => {
    if (!parsed.ok) return;
    onSubmit(parsed.obj);
  };

  const fields = plugin?.manifest?.config_schema ?? {};
  const fieldList = Object.entries(fields);

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="lg">
        <ModalHeader>
          <ModalTitle>
            插件配置 ·{' '}
            <span className="font-mono text-[12.5px]">
              {plugin?.plugin_key ?? ''}
            </span>
          </ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-3">
          {fieldList.length > 0 && (
            <div className="rounded-md border border-stone-200/70 bg-stone-50/60 px-3 py-2 text-[11px]">
              <div className="mb-1 text-[10.5px] uppercase tracking-wider text-stone-500">
                manifest config_schema
              </div>
              <ul className="space-y-0.5 text-stone-700">
                {fieldList.map(([k, f]) => (
                  <li key={k}>
                    <span className="font-mono">{k}</span>
                    <span className="ml-1 text-stone-400">
                      ({f.type ?? 'string'}
                      {f.required ? ', required' : ''}
                      {f.sensitive ? ', sensitive' : ''})
                    </span>
                    {f.description && (
                      <span className="ml-1 text-stone-500">— {f.description}</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="space-y-1.5">
            <Label>config（JSON）</Label>
            <textarea
              value={text}
              onChange={e => setText(e.target.value)}
              rows={14}
              className="w-full rounded-md border border-stone-300/70 bg-white px-2.5 py-1.5 font-mono text-[11.5px] text-stone-800 outline-none transition focus:border-primary-500 focus:ring-1 focus:ring-primary-200"
              spellCheck={false}
            />
            {!parsed.ok && (
              <div className="rounded border border-rose-200/70 bg-rose-50/60 px-2 py-1.5 text-[11px] text-rose-700">
                {parsed.error}
              </div>
            )}
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button
            variant="primary"
            disabled={!parsed.ok || loading}
            onClick={handleSubmit}
          >
            {loading ? '保存中…' : '保存'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};
