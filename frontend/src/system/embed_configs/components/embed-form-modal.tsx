/** 嵌入式智能体表单（创建 / 编辑共用）
 *
 * - 左侧 4-tab nav：基本 / 外观 / 行为 / 安全
 * - 中间表单
 * - 右侧静态预览（实时响应 ui_config + behavior）
 */
import { useEffect, useMemo, useState } from 'react';

import { useQuery } from '@tanstack/react-query';
import {
  Bot,
  Check,
  Code2,
  Cog,
  Copy,
  HelpCircle,
  MessageCircle,
  MessageSquare,
  Palette,
  Plus,
  Settings,
  ShieldCheck,
  Sparkles,
  Trash2,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

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
import { Switch } from '@/core/components/ui/switch';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import type { EntityId } from '@/core/types/api';
import { agentApi } from '@/system/agents/services/agent';
import { appApi } from '@/system/apps/services/app';
import { EmbedPreview } from '@/system/embed_configs/components/embed-preview';
import type {
  Behavior,
  BubbleIcon,
  BubblePosition,
  CreateEmbedConfigRequest,
  EmbedConfigItem,
  FontSize,
  ShadowLevel,
  ThemeMode,
  UiConfig,
  UpdateEmbedConfigRequest,
} from '@/system/embed_configs/types/embed';
import {
  DEFAULT_BEHAVIOR,
  DEFAULT_UI_CONFIG,
  mergeBehavior,
  mergeUiConfig,
} from '@/system/embed_configs/types/embed';

type TabKey = 'basic' | 'appearance' | 'behavior' | 'security' | 'access';

interface TabDef {
  key: TabKey;
  label: string;
  Icon: LucideIcon;
}

const TABS: TabDef[] = [
  { key: 'basic', label: '基本', Icon: Cog },
  { key: 'appearance', label: '外观', Icon: Palette },
  { key: 'behavior', label: '行为', Icon: Settings },
  { key: 'security', label: '安全', Icon: ShieldCheck },
  { key: 'access', label: '嵌入', Icon: Code2 },
];

interface EmbedFormModalProps {
  open: boolean;
  /** 传入即"编辑"模式；不传即"创建"模式 */
  initial?: EmbedConfigItem | null;
  loading: boolean;
  onClose: () => void;
  onSubmitCreate: (req: CreateEmbedConfigRequest) => void;
  onSubmitUpdate: (id: EntityId, req: UpdateEmbedConfigRequest) => void;
}

export const EmbedFormModal: React.FC<EmbedFormModalProps> = ({
  open,
  initial,
  loading,
  onClose,
  onSubmitCreate,
  onSubmitUpdate,
}) => {
  const isEdit = !!initial;
  const [tab, setTab] = useState<TabKey>('basic');

  // 基本
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [agentId, setAgentId] = useState<string>('');
  const [appId, setAppId] = useState<string>('');
  // 外观
  const [ui, setUi] = useState<UiConfig>(DEFAULT_UI_CONFIG);
  // 行为
  const [behavior, setBehavior] = useState<Behavior>(DEFAULT_BEHAVIOR);
  // 安全
  const [origins, setOrigins] = useState('');

  // 打开 / 切换 initial 时把外部 initial 同步进表单（合法的"开局重置"副作用）
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!open) return;
    setTab('basic');
    if (initial) {
      setName(initial.name);
      setDescription(initial.description || '');
      setAgentId(String(initial.agent_id));
      setAppId(String(initial.app_id));
      setUi(mergeUiConfig(initial.ui_config));
      setBehavior(mergeBehavior(initial.behavior));
      setOrigins((initial.allowed_origins || []).join('\n'));
    } else {
      setName('');
      setDescription('');
      setAgentId('');
      setAppId('');
      setUi(DEFAULT_UI_CONFIG);
      setBehavior(DEFAULT_BEHAVIOR);
      setOrigins('');
    }
  }, [open, initial]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const agentsQ = useQuery({ queryKey: ['agents', 'all'], queryFn: () => agentApi.list() });
  const appsQ = useQuery({
    queryKey: ['apps', 'all'],
    queryFn: () => appApi.list({ page: 1, page_size: 100 }),
  });

  const originList = useMemo(
    () =>
      origins
        .split('\n')
        .map(o => o.trim())
        .filter(Boolean),
    [origins],
  );

  const canSubmit = !!name && !!agentId && !!appId;

  const handleSubmit = () => {
    if (!canSubmit) return;
    if (isEdit && initial) {
      onSubmitUpdate(initial.id, {
        name,
        description: description || undefined,
        allowed_origins: originList,
        ui_config: ui,
        behavior,
      });
    } else {
      onSubmitCreate({
        name,
        description: description || undefined,
        agent_id: agentId,
        app_id: appId,
        allowed_origins: originList,
        ui_config: ui,
        behavior,
      });
    }
  };

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="xl" className="w-[1080px] max-w-[95vw]">
        <ModalHeader>
          <ModalTitle className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-blue-600" />
            {isEdit ? `编辑嵌入配置 · ${initial?.name}` : '新建嵌入配置'}
            {isEdit ? (
              <span className="font-mono text-[11px] font-normal text-stone-500">
                {initial?.embed_key}
              </span>
            ) : null}
          </ModalTitle>
        </ModalHeader>
        <ModalBody className="!p-0">
          <div className="flex h-[600px]">
            {/* tab nav */}
            <nav className="bg-warm-2/30 w-32 shrink-0 border-r border-stone-200/70 p-2">
              {TABS.map(t => (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => setTab(t.key)}
                  className={cn(
                    'mb-0.5 flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-[12.5px] font-medium transition',
                    tab === t.key
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-stone-600 hover:bg-stone-100',
                  )}
                >
                  <t.Icon className="h-3.5 w-3.5" strokeWidth={1.75} />
                  {t.label}
                </button>
              ))}
            </nav>

            {/* form area */}
            <div className="flex-1 overflow-y-auto px-5 py-4">
              {tab === 'basic' ? (
                <BasicTab
                  isEdit={isEdit}
                  name={name}
                  description={description}
                  agentId={agentId}
                  appId={appId}
                  agents={agentsQ.data || []}
                  apps={appsQ.data?.items || []}
                  onName={setName}
                  onDescription={setDescription}
                  onAgentId={setAgentId}
                  onAppId={setAppId}
                />
              ) : null}
              {tab === 'appearance' ? <AppearanceTab ui={ui} onChange={setUi} /> : null}
              {tab === 'behavior' ? <BehaviorTab v={behavior} onChange={setBehavior} /> : null}
              {tab === 'security' ? (
                <SecurityTab
                  origins={origins}
                  onChange={setOrigins}
                  originCount={originList.length}
                />
              ) : null}
              {tab === 'access' ? <AccessTab embedKey={initial?.embed_key ?? null} /> : null}
            </div>

            {/* preview */}
            <div className="w-[360px] shrink-0 border-l border-stone-200/70 bg-stone-50">
              <EmbedPreview ui={ui} behavior={behavior} />
            </div>
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button variant="primary" disabled={!canSubmit || loading} onClick={handleSubmit}>
            {loading ? '保存中...' : isEdit ? '保存修改' : '创建'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

// ── tabs ──────────────────────────────────────────────────────

interface AgentLite {
  id: EntityId;
  agent_key: string;
  name: string;
}
interface AppLite {
  id: EntityId;
  app_key: string;
  name: string;
}

const BasicTab: React.FC<{
  isEdit: boolean;
  name: string;
  description: string;
  agentId: string;
  appId: string;
  agents: AgentLite[];
  apps: AppLite[];
  onName: (v: string) => void;
  onDescription: (v: string) => void;
  onAgentId: (v: string) => void;
  onAppId: (v: string) => void;
}> = ({
  isEdit,
  name,
  description,
  agentId,
  appId,
  agents,
  apps,
  onName,
  onDescription,
  onAgentId,
  onAppId,
}) => (
  <div className="space-y-4">
    <Field label="名称" required>
      <Input value={name} onChange={e => onName(e.target.value)} placeholder="官网客服" />
    </Field>
    <Field label="描述" hint="自己看的备注，不展示给用户">
      <Textarea
        value={description}
        onChange={e => onDescription(e.target.value)}
        rows={2}
        placeholder="例：官网首页右下角的售前咨询入口"
      />
    </Field>
    <Field label="关联 Agent" required hint={isEdit ? '创建后不可改' : undefined}>
      <Select value={agentId} onValueChange={onAgentId} disabled={isEdit}>
        <SelectTrigger>
          <SelectValue placeholder="选择 agent" />
        </SelectTrigger>
        <SelectContent>
          {agents.map(a => (
            <SelectItem key={a.id} value={String(a.id)}>
              {a.agent_key} · {a.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
    <Field label="关联 App" required hint={isEdit ? '创建后不可改' : '用于配额计算 / 调用日志归属'}>
      <Select value={appId} onValueChange={onAppId} disabled={isEdit}>
        <SelectTrigger>
          <SelectValue placeholder="选择 app" />
        </SelectTrigger>
        <SelectContent>
          {apps.map(a => (
            <SelectItem key={a.id} value={String(a.id)}>
              {a.app_key} · {a.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  </div>
);

const BUBBLE_POSITION_OPTIONS: { value: BubblePosition; label: string }[] = [
  { value: 'right-bottom', label: '右下角' },
  { value: 'left-bottom', label: '左下角' },
  { value: 'right-top', label: '右上角' },
  { value: 'left-top', label: '左上角' },
];

const BUBBLE_ICON_OPTIONS: {
  value: BubbleIcon;
  label: string;
  Icon: LucideIcon;
}[] = [
  { value: 'chat', label: '对话气泡', Icon: MessageSquare },
  { value: 'sparkles', label: '星光', Icon: Sparkles },
  { value: 'help-circle', label: '问号', Icon: HelpCircle },
  { value: 'message-circle', label: '圆形气泡', Icon: MessageCircle },
  { value: 'bot', label: '机器人', Icon: Bot },
];

const MODE_OPTIONS: { value: ThemeMode; label: string }[] = [
  { value: 'light', label: '亮色' },
  { value: 'dark', label: '暗色' },
  { value: 'auto', label: '跟随系统' },
];

const FONT_SIZE_OPTIONS: { value: FontSize; label: string }[] = [
  { value: 'sm', label: '小' },
  { value: 'md', label: '中' },
  { value: 'lg', label: '大' },
];

const SHADOW_OPTIONS: { value: ShadowLevel; label: string }[] = [
  { value: 'none', label: '无' },
  { value: 'sm', label: '弱' },
  { value: 'md', label: '中' },
  { value: 'lg', label: '强' },
];

const EMOJI_PRESETS = ['🤖', '✨', '💬', '👋', '🦊', '🐼', '🧠', '🎯'];

const AppearanceTab: React.FC<{
  ui: UiConfig;
  onChange: (next: UiConfig) => void;
}> = ({ ui, onChange }) => {
  const patch = <K extends keyof UiConfig>(key: K, value: UiConfig[K]) =>
    onChange({ ...ui, [key]: value });

  return (
    <div className="space-y-5">
      <Section title="颜色">
        <div className="grid grid-cols-2 gap-3">
          <Field label="主色">
            <ColorInput value={ui.theme_color} onChange={v => patch('theme_color', v)} />
          </Field>
          <Field label="头部背景色">
            <ColorInput value={ui.header_bg} onChange={v => patch('header_bg', v)} />
          </Field>
          <Field label="浮窗按钮色">
            <ColorInput value={ui.bubble_color} onChange={v => patch('bubble_color', v)} />
          </Field>
          <Field label="主题模式">
            <Select value={ui.mode} onValueChange={v => patch('mode', v as ThemeMode)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MODE_OPTIONS.map(o => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>
      </Section>

      <Section title="文案">
        <Field label="头像 emoji">
          <div className="flex flex-wrap items-center gap-1.5">
            <Input
              value={ui.icon_emoji}
              onChange={e => patch('icon_emoji', e.target.value)}
              className="w-20 text-center text-[16px]"
              maxLength={4}
            />
            {EMOJI_PRESETS.map(e => (
              <button
                key={e}
                type="button"
                onClick={() => patch('icon_emoji', e)}
                className={cn(
                  'flex h-8 w-8 items-center justify-center rounded text-[16px] transition hover:bg-stone-100',
                  ui.icon_emoji === e ? 'bg-blue-50 ring-1 ring-blue-200' : '',
                )}
              >
                {e}
              </button>
            ))}
          </div>
        </Field>
        <Field label="标题">
          <Input value={ui.title} onChange={e => patch('title', e.target.value)} />
        </Field>
        <Field label="副标题">
          <Input value={ui.subtitle} onChange={e => patch('subtitle', e.target.value)} />
        </Field>
        <Field label="欢迎语" hint="assistant 首条招呼，支持换行">
          <Textarea
            rows={3}
            value={ui.greeting}
            onChange={e => patch('greeting', e.target.value)}
          />
        </Field>
        <Field label="输入框占位">
          <Input value={ui.placeholder} onChange={e => patch('placeholder', e.target.value)} />
        </Field>
      </Section>

      <Section title="浮窗 & 尺寸">
        <div className="grid grid-cols-2 gap-3">
          <Field label="浮窗位置">
            <Select
              value={ui.bubble_position}
              onValueChange={v => patch('bubble_position', v as BubblePosition)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {BUBBLE_POSITION_OPTIONS.map(o => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="浮窗图标">
            <Select
              value={ui.bubble_icon}
              onValueChange={v => patch('bubble_icon', v as BubbleIcon)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {BUBBLE_ICON_OPTIONS.map(o => (
                  <SelectItem key={o.value} value={o.value}>
                    <span className="inline-flex items-center gap-2">
                      <o.Icon className="h-3.5 w-3.5" /> {o.label}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="圆角">
            <NumberWithUnit
              value={ui.border_radius}
              onChange={v => patch('border_radius', v)}
              unit="px"
              min={0}
              max={32}
            />
          </Field>
          <Field label="阴影">
            <Select value={ui.shadow} onValueChange={v => patch('shadow', v as ShadowLevel)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SHADOW_OPTIONS.map(o => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="字体大小">
            <Select value={ui.font_size} onValueChange={v => patch('font_size', v as FontSize)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {FONT_SIZE_OPTIONS.map(o => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="面板宽度">
            <NumberWithUnit
              value={ui.panel_width}
              onChange={v => patch('panel_width', v)}
              unit="px"
              min={280}
              max={520}
            />
          </Field>
          <Field label="面板高度">
            <NumberWithUnit
              value={ui.panel_height}
              onChange={v => patch('panel_height', v)}
              unit="px"
              min={360}
              max={800}
            />
          </Field>
        </div>
      </Section>
    </div>
  );
};

const BehaviorTab: React.FC<{
  v: Behavior;
  onChange: (next: Behavior) => void;
}> = ({ v, onChange }) => {
  const patch = <K extends keyof Behavior>(key: K, value: Behavior[K]) =>
    onChange({ ...v, [key]: value });

  return (
    <div className="space-y-5">
      <Section title="启动">
        <ToggleField
          label="自动打开"
          hint="页面加载后自动弹出面板"
          checked={v.auto_open}
          onChange={c => patch('auto_open', c)}
        />
        {v.auto_open ? (
          <Field label="延迟" hint="单位：毫秒，0 = 立刻">
            <NumberWithUnit
              value={v.auto_open_delay_ms}
              onChange={n => patch('auto_open_delay_ms', n)}
              unit="ms"
              min={0}
              max={60000}
              step={500}
            />
          </Field>
        ) : null}
      </Section>

      <Section title="推荐问题" hint="点击直接发送，建议 2 ~ 4 条">
        <SuggestedQuestionsEditor
          items={v.suggested_questions}
          onChange={items => patch('suggested_questions', items)}
        />
      </Section>

      <Section title="回复行为">
        <ToggleField
          label="流式输出"
          hint="逐 token 推流，体验更顺滑"
          checked={v.streaming}
          onChange={c => patch('streaming', c)}
        />
        <ToggleField
          label="显示引用来源"
          hint="基于 KB 检索时，标出引用片段"
          checked={v.show_citations}
          onChange={c => patch('show_citations', c)}
        />
        <ToggleField
          label="显示反馈按钮"
          hint="每条回答下展示点赞 / 点踩"
          checked={v.show_feedback}
          onChange={c => patch('show_feedback', c)}
        />
        <ToggleField
          label="允许附件上传"
          hint="输入框前显示回形针图标"
          checked={v.allow_file_upload}
          onChange={c => patch('allow_file_upload', c)}
        />
      </Section>
    </div>
  );
};

const SecurityTab: React.FC<{
  origins: string;
  originCount: number;
  onChange: (v: string) => void;
}> = ({ origins, originCount, onChange }) => (
  <div className="space-y-4">
    <Section title="域名白名单" hint="只允许这些 Origin 的页面嵌入；为空时拒绝所有跨域加载">
      <Textarea
        value={origins}
        onChange={e => onChange(e.target.value)}
        rows={8}
        placeholder={'https://example.com\nhttps://app.example.com'}
        className="font-mono text-xs"
      />
      <div className="text-[11.5px] text-stone-500">
        {originCount > 0 ? `当前 ${originCount} 条` : '为空 = 完全拒绝跨域'}
      </div>
    </Section>
  </div>
);

// ── 接入方式：JS Widget + iframe 代码片段 ──────────────────────
const AccessTab: React.FC<{ embedKey: string | null }> = ({ embedKey }) => {
  if (!embedKey) {
    return (
      <div className="rounded-lg border border-dashed border-stone-200 px-4 py-8 text-center text-[12.5px] text-stone-400">
        保存后可在此获取接入代码
      </div>
    );
  }
  const origin = window.location.origin;
  const script = `<script src="${origin}/widget.js" data-embed-key="${embedKey}" defer></script>`;
  const iframe = `<iframe src="${origin}/embed/${embedKey}" style="width:400px;height:600px;border:0;border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,.1)"></iframe>`;
  return (
    <div className="space-y-3">
      <SnippetCard title="JS Widget" hint="推荐：右下角浮动气泡" code={script} />
      <SnippetCard title="iframe" hint="嵌入到页面内某个区域" code={iframe} />
    </div>
  );
};

const SnippetCard: React.FC<{ title: string; hint: string; code: string }> = ({
  title,
  hint,
  code,
}) => {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="overflow-hidden rounded-lg border border-stone-200">
      <div className="flex items-center justify-between bg-stone-50 px-3 py-1.5">
        <span className="text-[12.5px] font-medium text-stone-800">
          {title}
          <span className="ml-1.5 text-[11px] font-normal text-stone-400">· {hint}</span>
        </span>
        <button
          type="button"
          onClick={copy}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11.5px] text-stone-500 transition hover:bg-stone-200/70 hover:text-stone-800"
        >
          {copied ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <pre className="overflow-x-auto px-3 py-2.5 font-mono text-[11.5px] leading-relaxed break-all whitespace-pre-wrap text-stone-700">
        {code}
      </pre>
    </div>
  );
};

// ── 子组件 ────────────────────────────────────────────────────

const Section: React.FC<{
  title: string;
  hint?: string;
  children: React.ReactNode;
}> = ({ title, hint, children }) => (
  <div className="space-y-2">
    <div className="flex items-baseline gap-2 border-b border-stone-200/60 pb-1.5">
      <div className="text-[12.5px] font-semibold text-stone-800">{title}</div>
      {hint ? <div className="text-[11px] text-stone-500">{hint}</div> : null}
    </div>
    <div className="space-y-3">{children}</div>
  </div>
);

const Field: React.FC<{
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}> = ({ label, hint, required, children }) => (
  <div className="space-y-1">
    <div className="flex items-baseline gap-1.5">
      <Label className="text-[12px] text-stone-700">
        {label}
        {required ? <span className="ml-0.5 text-rose-500">*</span> : null}
      </Label>
      {hint ? <span className="text-[10.5px] text-stone-400">· {hint}</span> : null}
    </div>
    {children}
  </div>
);

const ColorInput: React.FC<{ value: string; onChange: (v: string) => void }> = ({
  value,
  onChange,
}) => (
  <div className="flex items-center gap-2">
    <input
      type="color"
      value={value}
      onChange={e => onChange(e.target.value)}
      className="h-8 w-10 cursor-pointer rounded border border-stone-200"
    />
    <Input
      value={value.toUpperCase()}
      onChange={e => onChange(e.target.value)}
      className="font-mono text-[11.5px] uppercase"
      maxLength={9}
    />
  </div>
);

const NumberWithUnit: React.FC<{
  value: number;
  onChange: (v: number) => void;
  unit: string;
  min?: number;
  max?: number;
  step?: number;
}> = ({ value, onChange, unit, min, max, step }) => (
  <div className="relative">
    <Input
      type="number"
      value={value}
      min={min}
      max={max}
      step={step}
      onChange={e => {
        const n = Number(e.target.value);
        if (Number.isFinite(n)) onChange(n);
      }}
      className="pr-10"
    />
    <span className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-[11px] text-stone-400">
      {unit}
    </span>
  </div>
);

const ToggleField: React.FC<{
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (c: boolean) => void;
}> = ({ label, hint, checked, onChange }) => (
  <div className="bg-paper flex items-center justify-between rounded-md border border-stone-200/60 px-3 py-2">
    <div className="space-y-0.5">
      <div className="text-[12.5px] font-medium text-stone-800">{label}</div>
      {hint ? <div className="text-[11px] text-stone-500">{hint}</div> : null}
    </div>
    <Switch checked={checked} onCheckedChange={onChange} />
  </div>
);

const SuggestedQuestionsEditor: React.FC<{
  items: string[];
  onChange: (items: string[]) => void;
}> = ({ items, onChange }) => {
  const set = (i: number, v: string) => onChange(items.map((it, idx) => (idx === i ? v : it)));
  const remove = (i: number) => onChange(items.filter((_, idx) => idx !== i));
  const add = () => onChange([...items, '']);
  return (
    <div className="space-y-1.5">
      {items.map((q, i) => (
        <div key={i} className="flex items-center gap-1.5">
          <Input
            value={q}
            onChange={e => set(i, e.target.value)}
            placeholder={`推荐问题 ${i + 1}`}
            className="flex-1"
          />
          <button
            type="button"
            onClick={() => remove(i)}
            className="rounded p-1.5 text-stone-400 transition hover:bg-stone-100 hover:text-rose-600"
            title="删除"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={add} disabled={items.length >= 8}>
        <Plus className="h-3.5 w-3.5" /> 添加推荐问题
      </Button>
      {items.length >= 8 ? <div className="text-[10.5px] text-stone-400">最多 8 条</div> : null}
    </div>
  );
};
