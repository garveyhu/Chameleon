/** 工作流编辑器左侧应用栏 —— Dify 套路：应用信息 + 二级导航 + Web App/后端API/MCP 卡片
 *
 * 编辑器整屏后，这条栏取代全局后台侧栏，提供「应用级」上下文：
 *   - 应用头：返回 / 图标 / 名称 / 类型切换 / key / 发布状态 / 保存状态
 *   - 二级导航：编排 / 访问 API / 日志 / 监测
 *   - 应用卡片：Web App（对话/嵌入）、后端服务 API（端点+密钥+文档）、MCP（占位）
 */
import { useState } from 'react';

import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Activity,
  ChevronLeft,
  ChevronsLeft,
  ChevronsRight,
  Code2,
  Copy,
  ExternalLink,
  Globe,
  KeyRound,
  Layers,
  type LucideIcon,
  MessageSquare,
  Rocket,
  Server,
  Settings,
  Sliders,
  Workflow,
} from 'lucide-react';

import { Popover, PopoverContent, PopoverTrigger } from '@/core/components/ui/popover';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { AgentHelperModelField } from '@/system/agents/components/agent-helper-model-field';
import { agentApi } from '@/system/agents/services/agent';
import { EmbedFormModal } from '@/system/embed_configs/components/embed-form-modal';
import { embedConfigApi } from '@/system/embed_configs/services/embed';
import type { EmbedConfigItem, UpdateEmbedConfigRequest } from '@/system/embed_configs/types/embed';
import { AgentKeysModal } from '@/system/graphs/components/app-shell/agent-keys-modal';
import { WebAppDialog, type WebAppTab } from '@/system/graphs/components/app-shell/web-app-dialogs';
import { EnumSelect } from '@/system/graphs/components/spec-fields';
import { graphApi } from '@/system/graphs/services/graph';
import type { GraphDetail, GraphKind, WebAppInfo } from '@/system/graphs/types/graph';

export type EditorTab = 'orchestrate' | 'api' | 'monitor';

// 访问 API 不在二级导航——由下方「后端服务 API」卡片的「API 文档」入口覆盖
// 日志已并入「监测」（监测视图内两个子 tab：日志 / 监测）
const NAV: { key: EditorTab; label: string; icon: LucideIcon }[] = [
  { key: 'orchestrate', label: '编排', icon: Layers },
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

  const [collapsed, setCollapsed] = useState(false);
  const [dialogTab, setDialogTab] = useState<WebAppTab | null>(null);
  const [embedCfg, setEmbedCfg] = useState<EmbedConfigItem | null>(null);
  const [keysOpen, setKeysOpen] = useState(false);
  const [webApp, setWebApp] = useState<WebAppInfo | null>(null);

  // 反查该 graph 对应的 agent —— graph 应用编辑器没经过应用详情页，
  // 这里把 agent.default_model_code 拉过来直接 inline 编辑，避免用户跳转
  const graphAgentsQ = useQuery({
    queryKey: ['agents', 'graph'],
    queryFn: () => agentApi.list({ source: 'graph' }),
    staleTime: 60_000,
  });
  const linkedAgent = (graphAgentsQ.data ?? []).find(a => a.graph_id === graph.id) ?? null;

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

  if (collapsed) {
    return (
      <>
        <aside className="bg-warm-2/50 flex h-screen w-12 shrink-0 flex-col items-center gap-1 border-r border-stone-200/70 px-2 py-3 transition-[width]">
          <button
            type="button"
            onClick={() => setCollapsed(false)}
            title="展开应用栏"
            className="rounded p-1 text-stone-400 transition hover:bg-stone-100 hover:text-stone-700"
          >
            <ChevronsRight className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onReturn}
            title="返回应用"
            className="rounded-md p-2 text-stone-500 transition hover:bg-stone-100 hover:text-stone-800"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <div className="my-1 h-px w-6 bg-stone-200/70" />
          {NAV.map(n => (
            <button
              key={n.key}
              type="button"
              onClick={() => onTab(n.key)}
              title={n.label}
              className={cn(
                'rounded-md p-2 transition',
                tab === n.key
                  ? 'bg-stone-900 text-white'
                  : 'text-stone-600 hover:bg-stone-100 hover:text-stone-900',
              )}
            >
              <n.icon className="h-4 w-4" />
            </button>
          ))}
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
        <AgentKeysModal graphId={graph.id} open={keysOpen} onClose={() => setKeysOpen(false)} />
      </>
    );
  }

  return (
    <>
      <aside className="bg-warm-2/50 flex h-screen w-64 shrink-0 flex-col border-r border-stone-200/70 transition-[width]">
        {/* 应用头 */}
        <div className="border-b border-stone-200/70 p-3">
          <div className="mb-2 flex items-center justify-between">
            <button
              type="button"
              onClick={onReturn}
              className="inline-flex items-center gap-1 text-[11.5px] text-stone-500 transition hover:text-stone-800"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              返回应用
            </button>
            <div className="flex items-center gap-0.5">
              {linkedAgent && (
                <Popover>
                  <PopoverTrigger asChild>
                    <button
                      type="button"
                      title="应用设置（辅助模型）"
                      className="rounded p-1 text-stone-400 transition hover:bg-stone-100 hover:text-stone-700"
                    >
                      <Sliders className="h-4 w-4" />
                    </button>
                  </PopoverTrigger>
                  <PopoverContent side="right" align="start" sideOffset={8} className="w-72 p-3">
                    <div className="mb-2 text-[12px] font-medium text-stone-800">应用设置</div>
                    <div className="space-y-3">
                      <div>
                        <div className="text-[11px] font-medium text-stone-600">辅助模型</div>
                        <AgentHelperModelField agent={linkedAgent} compact />
                      </div>
                    </div>
                  </PopoverContent>
                </Popover>
              )}
              <button
                type="button"
                onClick={() => setCollapsed(true)}
                title="收起应用栏"
                className="rounded p-1 text-stone-400 transition hover:bg-stone-100 hover:text-stone-700"
              >
                <ChevronsLeft className="h-4 w-4" />
              </button>
            </div>
          </div>
          <div className="flex items-start gap-2.5">
            <span
              className={cn(
                'flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-lg',
                graph.icon
                  ? 'bg-stone-100'
                  : isChat
                    ? 'bg-violet-100 text-violet-600'
                    : 'bg-sky-100 text-sky-600',
              )}
            >
              {graph.icon ? (
                <img src={graph.icon} alt="" className="h-full w-full object-cover" />
              ) : isChat ? (
                <MessageSquare className="h-4 w-4" />
              ) : (
                <Workflow className="h-4 w-4" />
              )}
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
            <button
              type="button"
              onClick={() => copy(apiBase, 'API 端点')}
              className="flex w-full items-center gap-1 rounded border border-stone-200 bg-white px-1.5 py-1 text-left font-mono text-[10px] text-stone-600 transition hover:bg-stone-50"
            >
              <span className="min-w-0 flex-1 truncate">{apiBase}</span>
              <Copy className="h-3 w-3 shrink-0 opacity-50" />
            </button>
            <div className="mt-1.5 flex gap-1.5">
              <RailAction label="API 文档" icon={Code2} onClick={() => onTab('api')} />
              <RailAction label="API 密钥" icon={KeyRound} onClick={() => setKeysOpen(true)} />
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
      <AgentKeysModal graphId={graph.id} open={keysOpen} onClose={() => setKeysOpen(false)} />
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
