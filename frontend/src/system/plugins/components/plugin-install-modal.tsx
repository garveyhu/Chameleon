/** Plugin 安装 Modal —— 粘贴 manifest JSON + 选 source + 立刻装载
 *
 * MVP：admin 先把插件包 pip install 到 venv，然后贴 manifest JSON 注册即可。
 * git / pypi 源仅记录 source_url 作元数据，不实际拉取（避免在主进程跑 pip）。
 * 上传 .tar.gz 等重逻辑留后续 PR。
 */

import { useMemo, useState } from 'react';

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
  InstallPluginPayload,
  PluginManifest,
} from '@/system/plugins/types/plugin';
import { PLUGIN_SOURCE_OPTIONS } from '@/system/plugins/types/plugin';

const MANIFEST_EXAMPLE = JSON.stringify(
  {
    name: 'openrouter',
    version: '1.0.0',
    type: 'provider',
    entrypoint: 'openrouter_chameleon.provider:OpenRouterProvider',
    chameleon_version: '>=0.5',
    description: 'OpenRouter API 接入',
    permissions: { network: true },
    config_schema: {
      api_key: { type: 'string', required: true, sensitive: true },
    },
  },
  null,
  2,
);

interface PluginInstallModalProps {
  open: boolean;
  loading: boolean;
  onClose: () => void;
  onSubmit: (payload: InstallPluginPayload) => void;
}

export const PluginInstallModal: React.FC<PluginInstallModalProps> = ({
  open,
  loading,
  onClose,
  onSubmit,
}) => {
  const [manifestText, setManifestText] = useState('');
  const [source, setSource] = useState<'local' | 'git' | 'pypi'>('local');
  const [sourceUrl, setSourceUrl] = useState('');

  // 实时解析 manifest，给用户预览
  const parsed = useMemo(() => {
    const text = manifestText.trim();
    if (!text) return { ok: false as const, error: '' };
    try {
      const obj = JSON.parse(text) as PluginManifest;
      if (!obj.name || !obj.version || !obj.type || !obj.entrypoint) {
        return {
          ok: false as const,
          error: 'manifest 缺少必填字段（name/version/type/entrypoint）',
        };
      }
      return { ok: true as const, manifest: obj };
    } catch (e) {
      return { ok: false as const, error: `JSON 解析失败: ${(e as Error).message}` };
    }
  }, [manifestText]);

  const reset = () => {
    setManifestText('');
    setSource('local');
    setSourceUrl('');
  };

  const handleClose = () => {
    if (loading) return;
    reset();
    onClose();
  };

  const canSubmit =
    parsed.ok &&
    !loading &&
    (source === 'local' || sourceUrl.trim().length > 0);

  const handleSubmit = () => {
    if (!parsed.ok || !canSubmit) return;
    onSubmit({
      manifest: parsed.manifest,
      source,
      source_url: source === 'local' ? null : sourceUrl.trim(),
    });
  };

  return (
    <Modal open={open} onOpenChange={o => !o && handleClose()}>
      <ModalContent size="lg">
        <ModalHeader>
          <ModalTitle>安装插件</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          <div className="rounded-md border border-amber-200/70 bg-amber-50/60 px-3 py-2 text-[11.5px] text-amber-800">
            插件包需先 <span className="font-mono">pip install</span> 到后端 venv，
            否则 entrypoint 加载会失败。沙箱已禁止 entrypoint 指向{' '}
            <span className="font-mono">chameleon.core.*</span> 等内部模块。
          </div>

          <div className="space-y-1.5">
            <Label>
              Manifest JSON <span className="text-rose-500">*</span>
              <span className="ml-1 text-[11px] text-stone-400">
                · 含 name / version / type / entrypoint
              </span>
            </Label>
            <textarea
              value={manifestText}
              onChange={e => setManifestText(e.target.value)}
              placeholder={MANIFEST_EXAMPLE}
              rows={12}
              className="w-full rounded-md border border-stone-300/70 bg-white px-2.5 py-1.5 font-mono text-[11.5px] text-stone-800 outline-none transition focus:border-primary-500 focus:ring-1 focus:ring-primary-200"
              spellCheck={false}
            />
            {parsed.ok ? (
              <div className="rounded border border-emerald-200/70 bg-emerald-50/60 px-2 py-1.5 text-[11px]">
                <div className="text-emerald-700">
                  ✓ {parsed.manifest.name} v{parsed.manifest.version} ·{' '}
                  {parsed.manifest.type}
                </div>
                <div className="mt-0.5 font-mono text-stone-600">
                  entrypoint: {parsed.manifest.entrypoint}
                </div>
              </div>
            ) : (
              manifestText.trim() && (
                <div className="rounded border border-rose-200/70 bg-rose-50/60 px-2 py-1.5 text-[11px] text-rose-700">
                  {parsed.error}
                </div>
              )
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>来源</Label>
              <Select
                value={source}
                onValueChange={v => setSource(v as typeof source)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PLUGIN_SOURCE_OPTIONS.map(o => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {source !== 'local' && (
              <div className="space-y-1.5">
                <Label>
                  Source URL{' '}
                  <span className="text-rose-500">*</span>
                </Label>
                <Input
                  value={sourceUrl}
                  onChange={e => setSourceUrl(e.target.value)}
                  placeholder={
                    source === 'git'
                      ? 'https://github.com/org/plugin.git'
                      : 'pypi:my-plugin'
                  }
                  className="font-mono text-[11.5px]"
                  maxLength={512}
                />
              </div>
            )}
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={handleClose} disabled={loading}>
            取消
          </Button>
          <Button
            variant="primary"
            disabled={!canSubmit}
            onClick={handleSubmit}
          >
            {loading ? '安装中…' : '安装'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};
