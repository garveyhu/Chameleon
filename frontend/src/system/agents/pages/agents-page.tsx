/** 应用卡片库：统一展示可被调用的 AI 能力（代码 / 对话流 / 流程 / 外部）
 *
 * 一个「应用」融三个侧面：图类应用（编排方式）+ 嵌入（投放渠道）。
 *   - 卡片网格（Dify 风，对齐知识库 kbs-page），不是表格
 *   - 数据合并 / 去重：见 useAppCards
 *   - 行为分流：图类 → graph 编辑器；代码/外部 → agent 详情页
 *   - 嵌入：从卡片操作进入，复用 embed_configs 的表单弹窗（不在主导航）
 *   - 新建应用：Dify 式编排方式选择器（对话/流程 → 建 graph 跳编辑器；代码 → 指引）
 */
import { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Boxes,
  Code2,
  Globe,
  ImagePlus,
  LayoutGrid,
  MessageSquare,
  Plus,
  Search,
  Workflow,
  X,
} from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import { confirm } from '@/core/lib/confirm';
import { fileToIconDataUrl } from '@/core/lib/image';
import type { OrchestrationKind } from '@/core/lib/orchestration';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { AppCard } from '@/system/agents/components/app-card';
import { type AppCard as AppCardModel, useAppCards } from '@/system/agents/hooks/useAppCards';
import { agentApi } from '@/system/agents/services/agent';
import { EmbedFormModal } from '@/system/embed_configs/components/embed-form-modal';
import { embedConfigApi } from '@/system/embed_configs/services/embed';
import type {
  CreateEmbedConfigRequest,
  EmbedConfigItem,
  UpdateEmbedConfigRequest,
} from '@/system/embed_configs/types/embed';
import { graphApi } from '@/system/graphs/services/graph';
import type { GraphKind, GraphSpec } from '@/system/graphs/types/graph';

// ── 新建工作流初始 spec ──────────────────────────────────────
/** 流程型：空管线（start → end），自己往里拖节点 */
const WORKFLOW_SPEC: GraphSpec = {
  nodes: [
    { id: 'start', type: 'start', name: 'Start', position: { x: 80, y: 200 } },
    { id: 'end', type: 'end', name: 'End', position: { x: 480, y: 200 } },
  ],
  edges: [{ id: 'e_start_end', source: 'start', target: 'end' }],
};

/** 对话型：开箱即聊（start → LLM → end），建完即可对话调试 */
const CHATFLOW_SPEC: GraphSpec = {
  nodes: [
    {
      id: 'start',
      type: 'start',
      name: 'Start',
      position: { x: 80, y: 200 },
      data: { opener: '你好！我是你的智能助理，有什么可以帮你？' },
    },
    {
      id: 'llm',
      type: 'llm',
      name: '对话',
      position: { x: 340, y: 200 },
      data: { system_prompt: '你是一个有帮助的中文助理，回答简洁、友好。' },
    },
    { id: 'end', type: 'end', name: 'End', position: { x: 600, y: 200 } },
  ],
  edges: [
    { id: 'e_start_llm', source: 'start', target: 'llm' },
    { id: 'e_llm_end', source: 'llm', target: 'end' },
  ],
};

// ── 类型筛选 ─────────────────────────────────────────────────
type KindFilter = 'all' | OrchestrationKind;

const KIND_FILTERS: { key: KindFilter; label: string; icon: typeof MessageSquare }[] = [
  { key: 'all', label: '全部', icon: LayoutGrid },
  { key: 'workflow', label: '流程型', icon: Workflow },
  { key: 'chatflow', label: '对话型', icon: MessageSquare },
  { key: 'code', label: '代码型', icon: Code2 },
  { key: 'external', label: '外部', icon: Globe },
];

export const AgentsPage = () => {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [kindFilter, setKindFilter] = useState<KindFilter>('all');
  const [keyword, setKeyword] = useState('');
  /** 嵌入操作目标：已存在的 embed 配置（编辑），或仅 agentId（新建） */
  const [embedTarget, setEmbedTarget] = useState<
    { initial: EmbedConfigItem | null; agentId: EntityId } | null
  >(null);
  /** 编辑目标卡片（头像 / 名称 / 描述） */
  const [editTarget, setEditTarget] = useState<AppCardModel | null>(null);

  const { cards, isLoading } = useAppCards();

  const counts = useMemo(() => {
    const acc: Record<KindFilter, number> = {
      all: cards.length,
      code: 0,
      chatflow: 0,
      workflow: 0,
      external: 0,
    };
    for (const c of cards) acc[c.kind] += 1;
    return acc;
  }, [cards]);

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return cards.filter(c => {
      if (kindFilter !== 'all' && c.kind !== kindFilter) return false;
      if (kw && !`${c.name} ${c.key} ${c.description ?? ''}`.toLowerCase().includes(kw)) {
        return false;
      }
      return true;
    });
  }, [cards, kindFilter, keyword]);

  /** 卡片分流：图类 → graph 编辑器；代码/外部 → agent 详情页 */
  const openCard = (c: AppCardModel) => {
    if (c.source === 'graph') {
      nav(`/graphs/${c.entityId}/edit`);
      return;
    }
    void qc.prefetchQuery({
      queryKey: ['agent', c.entityId],
      queryFn: () => agentApi.get(c.entityId),
    });
    nav(`/agents/${c.entityId}`);
  };

  /** 嵌入：已有该 agent 的 embed 配置则进编辑，否则带预选 agent 进新建 */
  const openEmbed = (c: AppCardModel) => {
    if (c.embedAgentId == null) {
      toast.error('该应用尚未发布，发布后才能配置嵌入');
      return;
    }
    const embeds = qc.getQueryData<{ items: EmbedConfigItem[] }>([
      'embed-configs',
      'all-for-cards',
    ]);
    const existing = embeds?.items.find(e => String(e.agent_id) === String(c.embedAgentId)) ?? null;
    setEmbedTarget({ initial: existing, agentId: c.embedAgentId });
  };

  const delMut = useMutation({
    mutationFn: async (c: AppCardModel) => {
      if (c.source === 'graph') await graphApi.delete(c.entityId);
      else await agentApi.delete(c.entityId);
    },
    onSuccess: () => {
      toast.success('已删除');
      qc.invalidateQueries({ queryKey: ['graphs'] });
      qc.invalidateQueries({ queryKey: ['agents'] });
      qc.invalidateQueries({ queryKey: ['embed-configs'] });
    },
  });

  const askDelete = async (c: AppCardModel) => {
    const ok = await confirm({
      title: `删除应用「${c.name}」？`,
      description:
        '将一并删除它的 API 密钥与嵌入配置；调用日志 / Trace 作为历史保留。此操作不可撤销。',
      confirmText: '删除',
      danger: true,
    });
    if (ok) delMut.mutate(c);
  };

  return (
    <div className="px-1">
      {/* 工具条：标题 + 筛选 tab + 搜索 + 新建 */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          {KIND_FILTERS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => setKindFilter(key)}
              className={cn(
                'flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[12px] font-medium transition',
                kindFilter === key
                  ? 'bg-blue-50 text-blue-700'
                  : 'text-stone-500 hover:bg-stone-100 hover:text-stone-700',
              )}
            >
              <Icon
                className={cn(
                  'h-3.5 w-3.5',
                  kindFilter === key ? 'text-blue-600' : 'text-stone-400',
                )}
              />
              {label}
              <span
                className={cn('text-[10px]', kindFilter === key ? 'text-blue-400' : 'text-stone-400')}
              >
                {counts[key]}
              </span>
            </button>
          ))}
        </div>

        <div className="relative ml-auto">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-stone-400" />
          <Input
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
            placeholder="搜索应用…"
            className="h-8 w-56 pl-8 text-[12.5px]"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {/* 创建入口卡 */}
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="group flex h-[148px] flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-stone-300 bg-white/60 text-stone-500 transition hover:border-blue-400 hover:bg-blue-50/40 hover:text-blue-600"
        >
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-stone-100 transition group-hover:bg-blue-100">
            <Plus className="h-5 w-5" strokeWidth={1.75} />
          </div>
          <span className="text-[13px] font-medium">新建应用</span>
          <span className="text-[11px] text-stone-400">对话 / 流程编排，或接入代码应用</span>
        </button>

        {/* 应用卡片 */}
        {filtered.map(c => (
          <AppCard
            key={c.cardId}
            card={c}
            onOpen={openCard}
            onEdit={setEditTarget}
            onEmbed={openEmbed}
            onDelete={askDelete}
          />
        ))}

        {/* 加载骨架 */}
        {isLoading &&
          cards.length === 0 &&
          Array.from({ length: 4 }).map((_, i) => (
            <div key={`skl-${i}`} className="skeleton h-[148px] rounded-xl opacity-60" />
          ))}
      </div>

      {!isLoading && filtered.length === 0 && cards.length > 0 ? (
        <div className="mt-8 text-center text-[12.5px] text-stone-400">没有匹配的应用</div>
      ) : null}

      <CreateAppModal open={createOpen} onClose={() => setCreateOpen(false)} />
      <EditAppModal card={editTarget} onClose={() => setEditTarget(null)} />
      <EmbedActionModal target={embedTarget} onClose={() => setEmbedTarget(null)} />
    </div>
  );
};

// ── 嵌入操作：复用 embed_configs 的表单弹窗 ──────────────────────
const EmbedActionModal = ({
  target,
  onClose,
}: {
  target: { initial: EmbedConfigItem | null; agentId: EntityId } | null;
  onClose: () => void;
}) => {
  const qc = useQueryClient();

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['embed-configs'] });
  };

  // 保存成功后不关弹窗 —— 用内部 state 跟踪当前编辑对象（创建后切到编辑模式 / 更新后回填最新数据）
  const [liveInitial, setLiveInitial] = useState<EmbedConfigItem | null>(target?.initial ?? null);
  useEffect(() => {
    // target 变化（开 / 关 / 切到另一张卡）→ 重置 internal
    setLiveInitial(target?.initial ?? null);
  }, [target]);

  const createMut = useMutation({
    mutationFn: (req: CreateEmbedConfigRequest) => embedConfigApi.create(req),
    onSuccess: created => {
      toast.success('嵌入配置已创建');
      invalidate();
      setLiveInitial(created); // 切到「编辑模式」，避免再点保存又新建一份
    },
  });
  const updateMut = useMutation({
    mutationFn: (args: { id: EntityId; req: UpdateEmbedConfigRequest }) =>
      embedConfigApi.update(args.id, args.req),
    onSuccess: updated => {
      toast.success('已保存');
      invalidate();
      setLiveInitial(updated); // 回填最新数据，允许连续修改
    },
  });

  return (
    <EmbedFormModal
      open={!!target}
      initial={liveInitial}
      presetAgentId={target?.agentId ?? null}
      loading={createMut.isPending || updateMut.isPending}
      onClose={onClose}
      onSubmitCreate={req => createMut.mutate(req)}
      onSubmitUpdate={(id, req) => updateMut.mutate({ id, req })}
    />
  );
};

// ── 编辑应用：头像 + 名称/描述（代码应用仅头像，名称/描述由代码定义）──────
const EditAppModal = ({ card, onClose }: { card: AppCardModel | null; onClose: () => void }) => {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [icon, setIcon] = useState('');
  const [lastId, setLastId] = useState<string | null>(null);

  // card 变化时同步初值（合法的 reset-on-prop-change）
  if (card && card.cardId !== lastId) {
    setLastId(card.cardId);
    setName(card.name);
    setDescription(card.description ?? '');
    setIcon(card.icon ?? '');
  }

  // 名称/描述：图类应用 + 外部应用可改；代码应用由代码定义，仅可改头像
  const nameEditable = !!card && (card.source === 'graph' || card.kind === 'external');

  const pickFile = async (file: File) => {
    if (!file.type.startsWith('image/')) {
      toast.error('请选择图片文件');
      return;
    }
    if (file.size > 4 * 1024 * 1024) {
      toast.error('图片过大，请选 4MB 以内');
      return;
    }
    try {
      setIcon(await fileToIconDataUrl(file));
    } catch {
      toast.error('图片读取失败');
    }
  };

  const saveMut = useMutation({
    mutationFn: async () => {
      if (!card) throw new Error('no card');
      const iconVal = icon === (card.icon ?? '') ? undefined : icon; // 空串 = 清除
      const payload = {
        name: nameEditable ? name.trim() : undefined,
        description: nameEditable ? description.trim() : undefined,
        icon: iconVal,
      };
      if (card.source === 'graph') await graphApi.update(card.entityId, payload);
      else await agentApi.update(card.entityId, payload);
    },
    onSuccess: () => {
      toast.success('已保存');
      qc.invalidateQueries({ queryKey: ['graphs'] });
      qc.invalidateQueries({ queryKey: ['agents'] });
      onClose();
    },
  });

  return (
    <Modal open={!!card} onOpenChange={o => !o && onClose()}>
      <ModalContent size="md">
        <ModalHeader>
          <ModalTitle>编辑应用</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-3">
          <div>
            <label className="mb-1 block text-[12px] text-stone-600">头像</label>
            <div className="flex items-center gap-3">
              <div className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-stone-100 text-stone-500">
                {icon ? (
                  <img src={icon} alt="" className="h-full w-full object-cover" />
                ) : (
                  <Boxes className="h-6 w-6" strokeWidth={1.6} />
                )}
              </div>
              <div className="flex flex-col gap-1.5">
                <Button
                  variant="ghost"
                  size="sm"
                  type="button"
                  onClick={() => fileRef.current?.click()}
                >
                  <ImagePlus className="mr-1.5 h-3.5 w-3.5" />
                  上传图片
                </Button>
                {icon && (
                  <button
                    type="button"
                    onClick={() => setIcon('')}
                    className="inline-flex items-center gap-1 text-[11px] text-stone-400 hover:text-rose-600"
                  >
                    <X className="h-3 w-3" />
                    移除，用默认图标
                  </button>
                )}
              </div>
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                hidden
                onChange={e => {
                  const f = e.target.files?.[0];
                  if (f) pickFile(f);
                  e.target.value = '';
                }}
              />
            </div>
            <p className="mt-1 text-[10.5px] text-stone-400">自动裁剪缩放为 128×128 小图</p>
          </div>

          {nameEditable ? (
            <>
              <div>
                <label className="mb-1 block text-[12px] text-stone-600">名称</label>
                <Input
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="应用名称"
                  className="h-8"
                />
              </div>
              <div>
                <label className="mb-1 block text-[12px] text-stone-600">描述</label>
                <Textarea
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  placeholder="一句话说明这个应用做什么"
                  rows={2}
                />
              </div>
            </>
          ) : (
            <p className="rounded-lg border border-stone-200 bg-stone-50 p-2.5 text-[11.5px] leading-relaxed text-stone-500">
              代码应用的名称 / 描述由代码定义，此处仅支持更换头像。
            </p>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button onClick={() => saveMut.mutate()} disabled={saveMut.isPending}>
            {saveMut.isPending ? '保存中…' : '保存'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

// ── 新建应用：编排方式选择器 ────────────────────────────────
type AppMethod = 'chatflow' | 'workflow' | 'code';

const METHOD_META: Record<
  AppMethod,
  { label: string; desc: string; icon: typeof MessageSquare }
> = {
  chatflow: {
    label: '对话编排',
    desc: '聊天 I/O + 开场白 + 对话调试，可发布为可对话应用',
    icon: MessageSquare,
  },
  workflow: {
    label: '流程编排',
    desc: '一次性管线：填输入跑、批处理；可视化拖拽节点',
    icon: Workflow,
  },
  code: {
    label: '代码应用',
    desc: '用 @agent 装饰器在代码里定义；提交进 agents 目录自动注册',
    icon: Code2,
  },
};

const CreateAppModal = ({ open, onClose }: { open: boolean; onClose: () => void }) => {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [method, setMethod] = useState<AppMethod>('chatflow');
  const [graphKey, setGraphKey] = useState('');
  const [graphName, setGraphName] = useState('');

  const reset = () => {
    setMethod('chatflow');
    setGraphKey('');
    setGraphName('');
  };

  const createMut = useMutation({
    mutationFn: (kind: GraphKind) =>
      graphApi.create({
        graph_key: graphKey.trim(),
        name: graphName.trim() || graphKey.trim(),
        kind,
        spec: kind === 'chatflow' ? CHATFLOW_SPEC : WORKFLOW_SPEC,
      }),
    onSuccess: g => {
      toast.success('已创建');
      qc.invalidateQueries({ queryKey: ['graphs'] });
      onClose();
      reset();
      nav(`/graphs/${g.id}/edit`);
    },
  });

  const isGraphMethod = method === 'chatflow' || method === 'workflow';

  return (
    <Modal
      open={open}
      onOpenChange={o => {
        if (!o) {
          reset();
          onClose();
        }
      }}
    >
      <ModalContent size="md">
        <ModalHeader>
          <ModalTitle>新建应用</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-3">
          <div>
            <label className="mb-1.5 block text-[12px] text-stone-600">编排方式</label>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              {(['chatflow', 'workflow', 'code'] as const).map(m => {
                const meta = METHOD_META[m];
                const Icon = meta.icon;
                const active = method === m;
                return (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setMethod(m)}
                    className={cn(
                      'rounded-lg border p-2.5 text-left transition',
                      active
                        ? 'border-stone-900 bg-stone-50 ring-1 ring-stone-900'
                        : 'border-stone-200 hover:border-stone-300 hover:bg-stone-50',
                    )}
                  >
                    <div className="flex items-center gap-1.5 text-[12.5px] font-medium text-stone-900">
                      <Icon className="h-3.5 w-3.5" />
                      {meta.label}
                    </div>
                    <div className="mt-1 text-[10.5px] leading-snug text-stone-500">
                      {meta.desc}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {isGraphMethod ? (
            <>
              <div>
                <label className="mb-1 block text-[12px] text-stone-600">
                  应用标识
                  <span className="ml-1 text-stone-400">（唯一；a-zA-Z0-9_-）</span>
                </label>
                <Input
                  value={graphKey}
                  onChange={e => setGraphKey(e.target.value)}
                  placeholder="my-app"
                  className="h-8 font-mono"
                />
              </div>
              <div>
                <label className="mb-1 block text-[12px] text-stone-600">显示名</label>
                <Input
                  value={graphName}
                  onChange={e => setGraphName(e.target.value)}
                  placeholder="留空时与应用标识一致"
                  className="h-8"
                />
              </div>
            </>
          ) : (
            <div className="rounded-lg border border-stone-200 bg-stone-50 p-3 text-[12px] leading-relaxed text-stone-600">
              <p className="font-medium text-stone-800">代码应用不在 Web 端创建</p>
              <p className="mt-1.5">
                用 <code className="rounded bg-stone-200 px-1 py-0.5 font-mono text-[11px]">@agent</code>{' '}
                装饰器定义你的智能体，把文件提交进项目的{' '}
                <code className="rounded bg-stone-200 px-1 py-0.5 font-mono text-[11px]">agents/</code>{' '}
                目录，平台会在加载时自动扫描入表，随后即可在本目录看到并配置。
              </p>
            </div>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          {isGraphMethod ? (
            <Button
              onClick={() => createMut.mutate(method)}
              disabled={!graphKey.trim() || createMut.isPending}
            >
              {createMut.isPending ? '创建中…' : '创建并编辑'}
            </Button>
          ) : (
            <Button onClick={onClose}>知道了</Button>
          )}
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};
