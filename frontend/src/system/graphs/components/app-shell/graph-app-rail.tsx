/** 工作流编辑器左侧应用栏 —— Dify 套路：应用信息 + 二级导航 + Web App/后端API/MCP 卡片
 *
 * 编辑器整屏后，这条栏取代全局后台侧栏，提供「应用级」上下文：
 *   - 应用头：返回 / 图标 / 名称 / 类型切换 / key / 发布状态 / 保存状态
 *   - 二级导航：编排 / 访问 API / 日志 / 监测
 *   - 应用卡片：Web App（对话/嵌入）、后端服务 API（端点+密钥+文档）、MCP（占位）
 */
import { useState } from 'react';

import { useMutation } from '@tanstack/react-query';
import {
  Activity,
  ChevronLeft,
  Code2,
  Copy,
  ExternalLink,
  Globe,
  KeyRound,
  Layers,
  type LucideIcon,
  MessageSquare,
  Rocket,
  ScrollText,
  Server,
  Settings,
  Workflow,
} from 'lucide-react';

import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { EmbedFormModal } from '@/system/embed_configs/components/embed-form-modal';
import { embedConfigApi } from '@/system/embed_configs/services/embed';
import type { EmbedConfigItem, UpdateEmbedConfigRequest } from '@/system/embed_configs/types/embed';
import { WebAppDialog, type WebAppTab } from '@/system/graphs/components/app-shell/web-app-dialogs';
import { EnumSelect } from '@/system/graphs/components/spec-fields';
import { graphApi } from '@/system/graphs/services/graph';
import type { GraphDetail, GraphKind, WebAppInfo } from '@/system/graphs/types/graph';

export type EditorTab = 'orchestrate' | 'api' | 'logs' | 'monitor';

const NAV: { key: EditorTab; label: string; icon: LucideIcon }[] = [
  { key: 'orchestrate', label: '编排', icon: Layers },
  { key: 'api', label: '访问 API', icon: Code2 },
  { key: 'logs', label: '日志', icon: ScrollText },
  { key: 'monitor', label: '监测', icon: Activity },
];

interface Props {
  graph: GraphDetail;
  kind: GraphKind;
  onKindChange: (k: GraphKind) => void;
  tab: EditorTab;
  onTab: (t: EditorTab) => void;
  onReturn: () => void;
  dirty: boolean;
  saving: boolean;
}

export const GraphAppRail = ({
  graph,
  kind,
  onKindChange,
  tab,
  onTab,
  onReturn,
  dirty,
  saving,
}: Props) => {
  const isChat = kind === 'chatflow';
  const published = (graph.published_version ?? 0) > 0;
  const apiBase = `${window.location.origin}/v1`;

  const [dialogTab, setDialogTab] = useState<WebAppTab | null>(null);
  const [embedCfg, setEmbedCfg] = useState<EmbedConfigItem | null>(null);
  const [webApp, setWebApp] = useState<WebAppInfo | null>(null);

  const updateEmbedMut = useMutation({
    mutationFn: (p: { id: EntityId; req: UpdateEmbedConfigRequest }) =>
      embedConfigApi.update(p.id, p.req),
    onSuccess: () => {
      setEmbedCfg(null);
      toast.success('已保存嵌入配置');
    },
    onError: e => toast.error(`保存失败：${(e as Error).message}`),
  });

  // 确保 Web App（embed）存在，拿到 embed_key；用途由 after 决定
  const ensureMut = useMutation({
    mutationFn: () => graphApi.ensureWebApp(graph.id),
    onError: e => toast.error(`Web App 初始化失败：${(e as Error).message}`),
  });
  const saveMut = useMutation({
    mutationFn: (payload: Parameters<typeof graphApi.updateWebApp>[1]) =>
      graphApi.updateWebApp(graph.id, payload),
    onSuccess: info => {
      setWebApp(info);
      setDialogTab(null);
      toast.success('已保存 Web App 设置');
    },
    onError: e => toast.error(`保存失败：${(e as Error).message}`),
  });

  const openPublicChat = async () => {
    const info = await ensureMut.mutateAsync();
    setWebApp(info);
    window.open(`${window.location.origin}/embed/${info.embed_key}`, '_blank');
  };
  const openDialog = async (tab: WebAppTab) => {
    const info = await ensureMut.mutateAsync();
    setWebApp(info);
    setDialogTab(tab);
  };
  const openEmbedApp = async () => {
    const info = await ensureMut.mutateAsync();
    setWebApp(info);
    try {
      const cfg = await embedConfigApi.get(info.id);
      setEmbedCfg(cfg);
    } catch (e) {
      toast.error(`加载嵌入配置失败：${(e as Error).message}`);
    }
  };

  const copy = (text: string, label: string) => {
    void navigator.clipboard.writeText(text).then(() => toast.success(`${label}已复制`));
  };

  return (
    <>
      <aside className="bg-warm-2/50 flex h-screen w-64 shrink-0 flex-col border-r border-stone-200/70">
        {/* 应用头 */}
        <div className="border-b border-stone-200/70 p-3">
          <button
            type="button"
            onClick={onReturn}
            className="mb-2 inline-flex items-center gap-1 text-[11.5px] text-stone-500 transition hover:text-stone-800"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
            返回工作流
          </button>
          <div className="flex items-start gap-2.5">
            <span
              className={cn(
                'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
                isChat ? 'bg-violet-100 text-violet-600' : 'bg-sky-100 text-sky-600',
              )}
            >
              {isChat ? <MessageSquare className="h-4 w-4" /> : <Workflow className="h-4 w-4" />}
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] font-semibold text-stone-900">{graph.name}</div>
              <div className="truncate font-mono text-[10.5px] text-stone-400">
                {graph.graph_key}
              </div>
            </div>
          </div>
          <div className="mt-2 flex items-center gap-1.5">
            <EnumSelect
              value={kind}
              onChange={v => onKindChange(v as GraphKind)}
              options={[
                { value: 'chatflow', label: '对话型' },
                { value: 'workflow', label: '流程型' },
              ]}
              className="h-6 w-[88px]"
            />
            {published ? (
              <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] text-emerald-700">
                <Rocket className="h-2.5 w-2.5" /> v{graph.published_version}
              </span>
            ) : (
              <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700">
                草稿
              </span>
            )}
            <span className="ml-auto text-[10px] text-stone-400">
              {saving ? '保存中…' : dirty ? '未保存' : '已保存'}
            </span>
          </div>
        </div>

        {/* 二级导航 */}
        <nav className="flex flex-col gap-0.5 p-2">
          {NAV.map(n => (
            <button
              key={n.key}
              type="button"
              onClick={() => onTab(n.key)}
              className={cn(
                'flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[12.5px] transition',
                tab === n.key
                  ? 'bg-stone-900 text-white'
                  : 'text-stone-600 hover:bg-stone-100 hover:text-stone-900',
              )}
            >
              <n.icon className="h-3.5 w-3.5" />
              {n.label}
            </button>
          ))}
        </nav>

        {/* 应用卡片 */}
        <div className="flex-1 space-y-2.5 overflow-y-auto border-t border-stone-200/70 p-2.5">
          {/* Web App / 嵌入 —— 公开聊天页 /embed/{key}，都在编辑器内完成 */}
          <Card
            icon={Globe}
            title="Web App"
            tone={isChat ? 'on' : 'off'}
            action={
              <button
                type="button"
                onClick={() => void openDialog('appearance')}
                title="Web App 配置"
                className="rounded p-0.5 text-stone-400 transition hover:bg-stone-100 hover:text-stone-700"
              >
                <Settings className="h-3.5 w-3.5" />
              </button>
            }
          >
            <div className="flex gap-1.5">
              <RailAction label="对话页打开" icon={ExternalLink} onClick={openPublicChat} />
              <RailAction label="嵌入式应用" icon={Code2} onClick={openEmbedApp} />
            </div>
          </Card>

          {/* 后端服务 API */}
          <Card icon={Server} title="后端服务 API" tone={isChat ? 'on' : 'off'}>
            <div className="text-[10px] text-stone-500">API 端点</div>
            <button
              type="button"
              onClick={() => copy(apiBase, 'API 端点')}
              className="mt-0.5 flex w-full items-center gap-1 rounded border border-stone-200 bg-white px-1.5 py-1 text-left font-mono text-[10px] text-stone-600 transition hover:bg-stone-50"
            >
              <span className="min-w-0 flex-1 truncate">{apiBase}</span>
              <Copy className="h-3 w-3 shrink-0 opacity-50" />
            </button>
            <div className="mt-1.5 flex gap-1.5">
              <RailAction label="API 文档" icon={Code2} onClick={() => onTab('api')} />
              <RailAction label="API 密钥" icon={KeyRound} onClick={() => onTab('api')} />
            </div>
          </Card>
        </div>
      </aside>

      {dialogTab && webApp && (
        <WebAppDialog
          open
          initialTab={dialogTab}
          onClose={() => setDialogTab(null)}
          info={webApp}
          onSave={p => saveMut.mutate(p)}
          saving={saveMut.isPending}
        />
      )}
      {embedCfg && (
        <EmbedFormModal
          open
          initial={embedCfg}
          loading={updateEmbedMut.isPending}
          onClose={() => setEmbedCfg(null)}
          onSubmitCreate={() => {}}
          onSubmitUpdate={(id, req) => updateEmbedMut.mutate({ id, req })}
        />
      )}
    </>
  );
};

// ── 小组件 ────────────────────────────────────────────────

const Card = ({
  icon: Icon,
  title,
  tone,
  action,
  children,
}: {
  icon: LucideIcon;
  title: string;
  tone: 'on' | 'off';
  action?: React.ReactNode;
  children: React.ReactNode;
}) => (
  <div className="rounded-lg border border-stone-200 bg-white p-2.5">
    <div className="mb-1.5 flex items-center gap-1.5">
      <Icon className="h-3.5 w-3.5 text-stone-500" />
      <span className="text-[12px] font-medium text-stone-800">{title}</span>
      {action}
      <span
        className={cn(
          'ml-auto inline-flex items-center gap-1 text-[10px]',
          tone === 'on' ? 'text-emerald-600' : 'text-stone-400',
        )}
      >
        <span
          className={cn(
            'h-1.5 w-1.5 rounded-full',
            tone === 'on' ? 'bg-emerald-500' : 'bg-stone-300',
          )}
        />
        {tone === 'on' ? '可用' : '未启用'}
      </span>
    </div>
    {children}
  </div>
);

const RailAction = ({
  label,
  onClick,
  icon: Icon,
}: {
  label: string;
  onClick: () => void;
  icon: LucideIcon;
}) => (
  <button
    type="button"
    onClick={onClick}
    className="flex flex-1 items-center justify-center gap-1 rounded-md bg-stone-100/80 px-2 py-1.5 text-[11px] text-stone-600 transition hover:bg-stone-200/70 hover:text-stone-900"
  >
    <Icon className="h-3 w-3 text-stone-400" />
    {label}
  </button>
);
