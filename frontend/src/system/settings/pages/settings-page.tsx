/** 系统配置 8-tab 页（DB-backed system_settings + model_defaults + 导入导出） */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  BookOpen,
  Cog,
  Download,
  FileText,
  Hourglass,
  MessagesSquare,
  Palette,
  Save,
  Sparkles,
  Upload,
  Waves,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { SectionCard } from '@/core/components/table';
import { Button } from '@/core/components/ui/button';
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
import { cn } from '@/core/lib/cn';
import { confirm } from '@/core/lib/confirm';
import { getRaw, postForm } from '@/core/lib/request';
import { toast } from '@/core/lib/toast';
import { modelApi } from '@/system/models/services/model';
import { AppearanceTab } from '@/system/settings/components/appearance-tab';
import { SettingsField } from '@/system/settings/components/settings-field';
import { settingsApi } from '@/system/settings/services/settings';

type SettingGroup = 'general' | 'session' | 'knowledge' | 'stream' | 'timeout' | 'call_log';
type TabKey = SettingGroup | 'model_defaults' | 'export_import' | 'appearance';

interface TabDef {
  key: TabKey;
  label: string;
  icon: React.ReactNode;
}

const TABS: TabDef[] = [
  { key: 'general', label: '通用', icon: <Cog className="h-3.5 w-3.5" /> },
  { key: 'session', label: '会话', icon: <MessagesSquare className="h-3.5 w-3.5" /> },
  { key: 'knowledge', label: '知识库默认', icon: <BookOpen className="h-3.5 w-3.5" /> },
  { key: 'stream', label: '流式', icon: <Waves className="h-3.5 w-3.5" /> },
  { key: 'timeout', label: '超时', icon: <Hourglass className="h-3.5 w-3.5" /> },
  { key: 'call_log', label: '调用日志', icon: <FileText className="h-3.5 w-3.5" /> },
  { key: 'model_defaults', label: '默认模型', icon: <Sparkles className="h-3.5 w-3.5" /> },
  { key: 'appearance', label: '外观', icon: <Palette className="h-3.5 w-3.5" /> },
  { key: 'export_import', label: '导入导出', icon: <Download className="h-3.5 w-3.5" /> },
];

export const SettingsPage = () => {
  useTranslation();
  const [activeTab, setActiveTab] = useState<TabKey>('general');

  return (
    <SectionCard className="!p-0">
      <div className="flex min-h-[600px]">
        <nav className="w-48 shrink-0 border-r border-stone-200/60 bg-warm-2/30 p-2">
          {TABS.map(tab => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                'flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-[12.5px] font-medium transition',
                activeTab === tab.key
                  ? 'bg-blue-50 text-blue-700'
                  : 'text-stone-600 hover:bg-stone-100',
              )}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </nav>
        <div className="flex-1 p-5">
          {(['general', 'session', 'knowledge', 'stream', 'timeout', 'call_log'] as const).includes(
            activeTab as SettingGroup,
          ) ? (
            <SystemSettingsTab group={activeTab as SettingGroup} />
          ) : null}
          {activeTab === 'model_defaults' ? <ModelDefaultsTab /> : null}
          {activeTab === 'appearance' ? <AppearanceTab /> : null}
          {activeTab === 'export_import' ? <ExportImportTab /> : null}
        </div>
      </div>
    </SectionCard>
  );
};

// ── system_settings tab ────────────────────────────────────────

const SystemSettingsTab = ({ group }: { group: SettingGroup }) => {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['system-settings'], queryFn: settingsApi.listSystem });
  const groupTitle = useMemo(() => TABS.find(t => t.key === group)?.label ?? group, [group]);
  const items = useMemo(
    () => (q.data?.items ?? []).filter(it => it.group === group),
    [q.data, group],
  );

  const [draft, setDraft] = useState<Record<string, unknown>>({});
  useEffect(() => {
    setDraft({}); // 切 group 时清 draft
  }, [group]);

  const liveValues = useMemo(() => {
    const out: Record<string, unknown> = {};
    for (const it of items) {
      out[it.key] = it.key in draft ? draft[it.key] : it.value;
    }
    return out;
  }, [items, draft]);

  const dirtyKeys = useMemo(() => {
    return items.filter(it => it.key in draft && draft[it.key] !== it.value).map(it => it.key);
  }, [items, draft]);

  const saveMut = useMutation({
    mutationFn: async () => {
      for (const k of dirtyKeys) {
        await settingsApi.updateSystem(k, draft[k]);
      }
    },
    onSuccess: () => {
      toast.success(`已保存 ${dirtyKeys.length} 项`);
      setDraft({});
      qc.invalidateQueries({ queryKey: ['system-settings'] });
    },
  });

  const resetMut = useMutation({
    mutationFn: (key: string) => settingsApi.resetSystem(key),
    onSuccess: () => {
      toast.success('已重置');
      setDraft({});
      qc.invalidateQueries({ queryKey: ['system-settings'] });
    },
  });

  const handleReset = async (key: string) => {
    const schema = items.find(it => it.key === key);
    const defaultText = schema ? String(schema.default ?? '—') : '默认值';
    const ok = await confirm({
      title: '重置为默认值？',
      description: `${key} 将清空 DB 中的覆盖记录，回到默认值（${defaultText}）。`,
      confirmText: '重置',
    });
    if (!ok) return;
    resetMut.mutate(key);
  };

  if (q.isLoading) {
    return <div className="text-[12.5px] text-stone-400">加载中...</div>;
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[14px] font-semibold text-stone-900">{groupTitle}</h3>
        <Button
          variant="primary"
          size="sm"
          disabled={dirtyKeys.length === 0 || saveMut.isPending}
          onClick={() => saveMut.mutate()}
        >
          <Save className="h-3.5 w-3.5" />
          {saveMut.isPending ? '保存中...' : `保存${dirtyKeys.length ? ` (${dirtyKeys.length})` : ''}`}
        </Button>
      </div>
      <div className="rounded-lg border border-stone-200/60 bg-paper px-4">
        {items.length === 0 ? (
          <div className="py-6 text-center text-[12.5px] text-stone-400">本组暂无配置项</div>
        ) : (
          items.map(item => (
            <SettingsField
              key={item.key}
              item={item}
              draftValue={liveValues[item.key]}
              onChange={(k, v) => setDraft(prev => ({ ...prev, [k]: v }))}
              onReset={handleReset}
            />
          ))
        )}
      </div>
    </div>
  );
};

// ── model defaults tab ─────────────────────────────────────────

const ModelDefaultsTab = () => {
  const qc = useQueryClient();
  const defaultsQ = useQuery({
    queryKey: ['model-defaults'],
    queryFn: settingsApi.listModelDefaults,
  });
  const modelsQ = useQuery({ queryKey: ['models'], queryFn: () => modelApi.list() });

  const updateMut = useMutation({
    mutationFn: (args: { case_name: string; model_id: import('@/core/types/api').EntityId | null }) =>
      settingsApi.updateModelDefault(args.case_name, args.model_id),
    onSuccess: () => {
      toast.success('已更新');
      qc.invalidateQueries({ queryKey: ['model-defaults'] });
    },
  });

  const llmModels = (modelsQ.data || []).filter(m => m.kind === 'chat' && m.enabled);
  const embeddingModels = (modelsQ.data || []).filter(m => m.kind === 'embedding' && m.enabled);

  const findCurrent = (c: string) =>
    (defaultsQ.data || []).find(d => d.case_name === c)?.model_id ?? null;

  if (defaultsQ.isLoading || modelsQ.isLoading) {
    return <div className="text-[12.5px] text-stone-400">加载中...</div>;
  }

  return (
    <div>
      <h3 className="mb-3 text-[14px] font-semibold text-stone-900">默认调用模型</h3>
      <p className="mb-4 text-[12px] text-stone-500">
        指定 agent 调用时不显式传 model 时，默认走哪个模型。embedding 影响知识库写入向量；vision 暂未启用。
      </p>
      <div className="rounded-lg border border-stone-200/60 bg-paper">
        <CaseRow
          label="LLM (chat)"
          value={findCurrent('llm')}
          options={llmModels.map(m => ({ id: m.id, name: m.code, provider: m.provider_code }))}
          onChange={id => updateMut.mutate({ case_name: 'llm', model_id: id })}
        />
        <CaseRow
          label="Embedding"
          value={findCurrent('embedding')}
          options={embeddingModels.map(m => ({
            id: m.id,
            name: m.code,
            provider: m.provider_code,
          }))}
          onChange={id => updateMut.mutate({ case_name: 'embedding', model_id: id })}
        />
        <CaseRow
          label="Vision（可选）"
          value={findCurrent('vision')}
          options={llmModels.map(m => ({ id: m.id, name: m.code, provider: m.provider_code }))}
          onChange={id => updateMut.mutate({ case_name: 'vision', model_id: id })}
          allowClear
        />
      </div>
    </div>
  );
};

const CaseRow = ({
  label,
  value,
  options,
  onChange,
  allowClear,
}: {
  label: string;
  value: import('@/core/types/api').EntityId | null;
  options: { id: import('@/core/types/api').EntityId; name: string; provider: string | null }[];
  onChange: (id: import('@/core/types/api').EntityId | null) => void;
  allowClear?: boolean;
}) => (
  <div className="flex items-center justify-between border-b border-stone-100 px-4 py-3 last:border-b-0">
    <div className="text-[13px] font-medium text-stone-800">{label}</div>
    <Select
      value={value === null ? '' : String(value)}
      onValueChange={v => onChange(v === '__clear__' ? null : Number(v))}
    >
      <SelectTrigger className="max-w-[280px]">
        <SelectValue placeholder="未设置" />
      </SelectTrigger>
      <SelectContent>
        {allowClear ? <SelectItem value="__clear__">未设置</SelectItem> : null}
        {options.map(o => (
          <SelectItem key={o.id} value={String(o.id)}>
            {o.name}
            {o.provider ? ` · ${o.provider}` : ''}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  </div>
);

// ── export / import tab ────────────────────────────────────────

const ExportImportTab = () => {
  const [warnOpen, setWarnOpen] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [importing, setImporting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const exportMut = useMutation({
    mutationFn: async () => {
      const { data, headers } = await getRaw<Blob>('/v1/admin/settings/export-json');
      const cd = headers['content-disposition'] || '';
      const m = cd.match(/filename="?([^"]+)"?/);
      const filename = m?.[1] || `chameleon-backup-${Date.now()}.zip`;
      const url = URL.createObjectURL(data);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      return filename;
    },
    onSuccess: f => {
      toast.success(`已下载 ${f}`);
      setWarnOpen(false);
      setAcknowledged(false);
    },
  });

  const handleImport = async (file: File) => {
    const ok = await confirm({
      title: '确认导入配置？',
      description: `将合并 ${file.name} 中的 apps / users / providers / models / agents / api_keys / embed_configs。同 key 行直接 UPSERT 覆盖，操作不可撤销。`,
      confirmText: '继续导入',
      danger: true,
    });
    if (!ok) return;
    setImporting(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('confirm', 'true');
      const result = await postForm<{
        apps_upserted: number;
        users_upserted: number;
        providers_upserted: number;
        models_upserted: number;
        agents_upserted: number;
        embed_configs_upserted: number;
        api_keys_upserted: number;
        warnings: string[];
      }>('/v1/admin/settings/import-json', fd);
      toast.success(
        `导入完成：apps ${result.apps_upserted} / users ${result.users_upserted} / providers ${result.providers_upserted} / models ${result.models_upserted} / agents ${result.agents_upserted}`,
      );
      if (result.warnings.length > 0) {
        toast.warning(`${result.warnings.length} 条警告，详见浏览器 console`);
        console.warn('Import warnings:', result.warnings);
      }
    } catch {
      // 全局拦截器已提示错误，无需重复
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  return (
    <div>
      <h3 className="mb-3 text-[14px] font-semibold text-stone-900">配置导入导出</h3>
      <p className="mb-4 text-[12px] leading-relaxed text-stone-500">
        导出 ZIP 含 <span className="font-mono">chameleon.json · model.json · agents.yaml · baseurl.json · users.json · apps.json · embed_configs.json</span>。
        <br />
        provider API Key 以<span className="font-medium text-red-600">明文</span>写入文件，便于迁移；
        请勿上传到 git / IM / 云盘。
      </p>
      <div className="flex gap-2">
        <Button variant="primary" size="sm" onClick={() => setWarnOpen(true)}>
          <Download className="h-3.5 w-3.5" />
          导出全部配置
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => fileRef.current?.click()}
          disabled={importing}
        >
          <Upload className="h-3.5 w-3.5" />
          {importing ? '导入中...' : '导入 ZIP'}
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept=".zip"
          className="hidden"
          onChange={e => {
            const file = e.target.files?.[0];
            if (file) handleImport(file);
          }}
        />
      </div>

      <Modal
        open={warnOpen}
        onOpenChange={o => {
          if (!o) {
            setWarnOpen(false);
            setAcknowledged(false);
          }
        }}
      >
        <ModalContent size="md">
          <ModalHeader>
            <ModalTitle className="flex items-center gap-2 text-amber-700">
              <AlertTriangle className="h-4 w-4" />
              导出包含敏感凭证
            </ModalTitle>
          </ModalHeader>
          <ModalBody className="space-y-3 text-[12.5px] leading-relaxed text-stone-600">
            <p>本次导出 ZIP 含：</p>
            <ul className="ml-4 list-disc space-y-0.5">
              <li>providers 的 <span className="font-mono text-red-600">明文 API Key</span></li>
              <li>users 的密码哈希（argon2id）</li>
              <li>apps 的 api_key 哈希（不可还原但仍属敏感数据）</li>
            </ul>
            <p>
              请<span className="font-semibold text-stone-800">勿上传到 git / IM / 公共云盘</span>。
              建议本地保管或走加密通道传输。
            </p>
            <label className="mt-3 flex cursor-pointer items-center gap-2 rounded-md border border-stone-200 p-2.5 hover:bg-stone-50">
              <input
                type="checkbox"
                className="h-3.5 w-3.5"
                checked={acknowledged}
                onChange={e => setAcknowledged(e.target.checked)}
              />
              <span className="text-[12.5px] text-stone-700">我已了解风险，继续导出</span>
            </label>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" onClick={() => setWarnOpen(false)}>
              取消
            </Button>
            <Button
              variant="primary"
              disabled={!acknowledged || exportMut.isPending}
              onClick={() => exportMut.mutate()}
            >
              <Download className="h-3.5 w-3.5" />
              {exportMut.isPending ? '导出中...' : '确认下载'}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </div>
  );
};
