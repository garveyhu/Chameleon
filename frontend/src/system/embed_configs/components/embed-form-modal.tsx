/** 嵌入式智能体表单（创建 / 编辑共用）
 *
 * - 左侧 4-tab nav：基本 / 外观 / 行为 / 安全
 * - 中间表单
 * - 右侧静态预览（实时响应 ui_config + behavior）
 */
import { useEffect, useMemo, useRef, useState } from 'react';

import { useQuery } from '@tanstack/react-query';
import {
  Bot,
  Check,
  Code2,
  Cog,
  Copy,
  HelpCircle,
  Loader2,
  MessageCircle,
  MessageSquare,
  MessagesSquare,
  Palette,
  Plus,
  Settings,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { Label } from '@/core/components/ui/label';
import { toast } from '@/core/lib/toast';
import { uploadFile } from '@/system/files/services/file-upload';
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
import { EmbedPreview } from '@/system/embed_configs/components/embed-preview';
import type {
  Behavior,
  BubbleIcon,
  BubblePosition,
  CreateEmbedConfigRequest,
  EmbedConfigItem,
  FileKind,
  FontSize,
  IdentificationMode,
  SessionPolicy,
  ShadowLevel,
  ThemeMode,
  UiConfig,
  UpdateEmbedConfigRequest,
} from '@/system/embed_configs/types/embed';
import {
  DEFAULT_BEHAVIOR,
  DEFAULT_SESSION_POLICY,
  DEFAULT_UI_CONFIG,
  mergeBehavior,
  mergeSessionPolicy,
  mergeUiConfig,
} from '@/system/embed_configs/types/embed';

type TabKey = 'basic' | 'appearance' | 'behavior' | 'session' | 'security' | 'access';

interface TabDef {
  key: TabKey;
  label: string;
  Icon: LucideIcon;
}

const TABS: TabDef[] = [
  { key: 'basic', label: '基本', Icon: Cog },
  { key: 'appearance', label: '外观', Icon: Palette },
  { key: 'behavior', label: '行为', Icon: Settings },
  { key: 'session', label: '会话', Icon: MessagesSquare },
  { key: 'security', label: '安全', Icon: ShieldCheck },
  { key: 'access', label: '嵌入', Icon: Code2 },
];

interface EmbedFormModalProps {
  open: boolean;
  /** 传入即"编辑"模式；不传即"创建"模式 */
  initial?: EmbedConfigItem | null;
  /** 创建模式下预选并锁定关联应用（从应用卡片「嵌入」操作进入时使用） */
  presetAgentId?: EntityId | null;
  loading: boolean;
  onClose: () => void;
  onSubmitCreate: (req: CreateEmbedConfigRequest) => void;
  onSubmitUpdate: (id: EntityId, req: UpdateEmbedConfigRequest) => void;
}

export const EmbedFormModal: React.FC<EmbedFormModalProps> = ({
  open,
  initial,
  presetAgentId,
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
  // 外观
  const [ui, setUi] = useState<UiConfig>(DEFAULT_UI_CONFIG);
  // 行为
  const [behavior, setBehavior] = useState<Behavior>(DEFAULT_BEHAVIOR);
  // 会话（S13）：身份模式 / 历史侧栏 / 用户自管 / 时间窗 + owner key
  const [sessionPolicy, setSessionPolicy] = useState<SessionPolicy>(DEFAULT_SESSION_POLICY);
  const [apiKeyId, setApiKeyId] = useState<EntityId | null>(null);
  // 安全
  const [origins, setOrigins] = useState('');

  // 弹窗刚开时把 tab 归到「基本」；initial 变化（保存后切到编辑模式 / 父组件传新数据）只回填字段，
  // 不动用户当前正在编辑的 tab —— 否则保存成功后从「外观」跳回「基本」打断 UX。
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (open) setTab('basic');
  }, [open]);
  useEffect(() => {
    if (!open) return;
    if (initial) {
      setName(initial.name);
      setDescription(initial.description || '');
      setAgentId(String(initial.agent_id));
      setUi(mergeUiConfig(initial.ui_config));
      setBehavior(mergeBehavior(initial.behavior));
      setSessionPolicy(mergeSessionPolicy(initial.session_policy));
      setApiKeyId(initial.api_key_id ?? null);
      setOrigins((initial.allowed_origins || []).join('\n'));
    } else {
      setName('');
      setDescription('');
      setAgentId(presetAgentId != null ? String(presetAgentId) : '');
      setUi(DEFAULT_UI_CONFIG);
      setBehavior(DEFAULT_BEHAVIOR);
      setSessionPolicy(DEFAULT_SESSION_POLICY);
      setApiKeyId(null);
      setOrigins('');
    }
  }, [open, initial, presetAgentId]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const agentsQ = useQuery({ queryKey: ['agents', 'all'], queryFn: () => agentApi.list() });

  const originList = useMemo(
    () =>
      origins
        .split('\n')
        .map(o => o.trim())
        .filter(Boolean),
    [origins],
  );

  const canSubmit = !!name && !!agentId;

  const handleSubmit = () => {
    if (!canSubmit) return;
    if (isEdit && initial) {
      onSubmitUpdate(initial.id, {
        name,
        description: description || undefined,
        api_key_id: apiKeyId,
        allowed_origins: originList,
        ui_config: ui,
        behavior,
        session_policy: sessionPolicy,
      });
    } else {
      onSubmitCreate({
        name,
        description: description || undefined,
        agent_id: agentId,
        api_key_id: apiKeyId,
        allowed_origins: originList,
        ui_config: ui,
        behavior,
        session_policy: sessionPolicy,
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
                  lockAgent={isEdit || presetAgentId != null}
                  lockHint={isEdit ? '创建后不可改' : presetAgentId != null ? '已锁定为当前应用' : undefined}
                  name={name}
                  description={description}
                  agentId={agentId}
                  agents={agentsQ.data || []}
                  onName={setName}
                  onDescription={setDescription}
                  onAgentId={setAgentId}
                />
              ) : null}
              {tab === 'appearance' ? <AppearanceTab ui={ui} onChange={setUi} /> : null}
              {tab === 'behavior' ? <BehaviorTab v={behavior} onChange={setBehavior} /> : null}
              {tab === 'session' ? (
                <SessionTab
                  agentId={agentId}
                  policy={sessionPolicy}
                  apiKeyId={apiKeyId}
                  onPolicy={setSessionPolicy}
                  onApiKeyId={setApiKeyId}
                />
              ) : null}
              {tab === 'security' ? (
                <SecurityTab
                  origins={origins}
                  onChange={setOrigins}
                  originCount={originList.length}
                />
              ) : null}
              {tab === 'access' ? (
                <AccessTab
                  embedKey={initial?.embed_key ?? null}
                  identificationMode={sessionPolicy.identification_mode}
                />
              ) : null}
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

const BasicTab: React.FC<{
  lockAgent: boolean;
  lockHint?: string;
  name: string;
  description: string;
  agentId: string;
  agents: AgentLite[];
  onName: (v: string) => void;
  onDescription: (v: string) => void;
  onAgentId: (v: string) => void;
}> = ({
  lockAgent,
  lockHint,
  name,
  description,
  agentId,
  agents,
  onName,
  onDescription,
  onAgentId,
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
    <Field label="关联 Agent" required hint={lockHint}>
      <Select value={agentId} onValueChange={onAgentId} disabled={lockAgent}>
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
  </div>
);

const BUBBLE_POSITION_OPTIONS: { value: BubblePosition; label: string }[] = [
  { value: 'right-bottom', label: '右下角' },
  { value: 'left-bottom', label: '左下角' },
  { value: 'right-top', label: '右上角' },
  { value: 'left-top', label: '左上角' },
];

const TOOLTIP_POSITION_OPTIONS: {
  value: UiConfig['bubble_tooltip_position'];
  label: string;
}[] = [
  { value: 'left', label: '左侧' },
  { value: 'right', label: '右侧' },
  { value: 'top', label: '上方' },
  { value: 'bottom', label: '下方' },
  // orbit（环绕浮窗）暂时下线：SVG textPath 字头方向兼容性差，先去掉再做
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

const AvatarPicker: React.FC<{
  iconUrl: string | null;
  iconEmoji: string;
  onChangeUrl: (next: string | null) => void;
  onChangeEmoji: (next: string) => void;
}> = ({ iconUrl, iconEmoji, onChangeUrl, onChangeEmoji }) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const handleSelect = async (file: File) => {
    if (!file.type.startsWith('image/')) {
      toast.error('请选择图片文件');
      return;
    }
    // 头像不需要大图，前端 2MB 软限（后端硬限 20MB）
    if (file.size > 2 * 1024 * 1024) {
      toast.error('头像图片不能超过 2MB');
      return;
    }
    setUploading(true);
    try {
      const res = await uploadFile(file, { namespace: 'embed-icons' });
      onChangeUrl(res.object_url);
    } catch (e) {
      toast.error(`上传失败：${(e as Error).message}`);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  return (
    <div className="space-y-2.5">
      {/* 当前头像预览 + 操作 */}
      <div className="flex items-center gap-3">
        <div className="flex h-14 w-14 items-center justify-center overflow-hidden rounded-lg border border-stone-200 bg-stone-50 text-[28px]">
          {iconUrl ? (
            <img src={iconUrl} alt="头像" className="h-full w-full object-cover" />
          ) : (
            <span>{iconEmoji || '🤖'}</span>
          )}
        </div>
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-1.5">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={e => {
                const f = e.target.files?.[0];
                if (f) void handleSelect(f);
              }}
            />
            <Button
              size="sm"
              variant="outline"
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? (
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Upload className="mr-1 h-3.5 w-3.5" />
              )}
              {iconUrl ? '更换图片' : '上传图片'}
            </Button>
            {iconUrl && (
              <Button
                size="sm"
                variant="ghost"
                type="button"
                onClick={() => onChangeUrl(null)}
                title="移除图片，使用 emoji"
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
          <span className="text-[11px] text-stone-400">PNG / JPG / SVG，≤ 2MB；不传则用 emoji</span>
        </div>
      </div>

      {/* emoji 回退选项（图片为空时生效） */}
      <div className={cn('flex flex-wrap items-center gap-1.5', iconUrl && 'opacity-50')}>
        <Input
          value={iconEmoji}
          onChange={e => onChangeEmoji(e.target.value)}
          className="w-20 text-center text-[16px]"
          maxLength={4}
          disabled={!!iconUrl}
        />
        {EMOJI_PRESETS.map(e => (
          <button
            key={e}
            type="button"
            onClick={() => onChangeEmoji(e)}
            disabled={!!iconUrl}
            className={cn(
              'flex h-8 w-8 items-center justify-center rounded text-[16px] transition hover:bg-stone-100 disabled:cursor-not-allowed',
              iconEmoji === e && !iconUrl ? 'bg-blue-50 ring-1 ring-blue-200' : '',
            )}
          >
            {e}
          </button>
        ))}
      </div>
    </div>
  );
};

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
          <Field label="头部文字颜色" hint="留空 / 透明值时按底色自动反色">
            <ColorInput
              value={ui.header_text_color}
              onChange={v => patch('header_text_color', v)}
            />
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
        <Field label="头像" hint="上传图片优先；未上传时使用 emoji">
          <AvatarPicker
            iconUrl={ui.icon_url}
            iconEmoji={ui.icon_emoji}
            onChangeUrl={v => patch('icon_url', v)}
            onChangeEmoji={v => patch('icon_emoji', v)}
          />
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

      <Section title="浮窗自定义" hint="大小 / 图片 / 透明背景 / 旁边招呼语 都可选">
        <div className="grid grid-cols-2 gap-3">
          <Field label="浮窗大小">
            <NumberWithUnit
              value={ui.bubble_size}
              onChange={v => patch('bubble_size', Math.max(40, Math.min(96, v)))}
              unit="px"
              min={40}
              max={96}
              step={4}
            />
          </Field>
        </div>
        <Field label="自定义图片" hint="圆形显示，建议正方形 PNG/JPG，≤ 2MB">
          <BubbleImagePicker
            value={ui.bubble_image_url}
            onChange={v => patch('bubble_image_url', v)}
          />
        </Field>
        <ToggleField
          label="透明背景"
          hint="去掉浮窗的纯色圆背景，仅显图标 / 图片本身"
          checked={ui.bubble_transparent}
          onChange={c => patch('bubble_transparent', c)}
        />
        <Field label="招呼语" hint="空字符串关闭；浮在浮窗旁边的文字（如 hi, 让我帮助你～）">
          <Input
            value={ui.bubble_tooltip_text}
            onChange={e => patch('bubble_tooltip_text', e.target.value)}
            placeholder="hi, 让我帮助你～"
            maxLength={40}
          />
        </Field>
        {ui.bubble_tooltip_text ? (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Field label="位置">
                <Select
                  value={ui.bubble_tooltip_position}
                  onValueChange={v =>
                    patch('bubble_tooltip_position', v as UiConfig['bubble_tooltip_position'])
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TOOLTIP_POSITION_OPTIONS.map(o => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="字号">
                <NumberWithUnit
                  value={ui.bubble_tooltip_font_size}
                  onChange={v => patch('bubble_tooltip_font_size', Math.max(10, Math.min(28, v)))}
                  unit="px"
                  min={10}
                  max={28}
                />
              </Field>
              <Field label="文字颜色">
                <ColorInput
                  value={ui.bubble_tooltip_color}
                  onChange={v => patch('bubble_tooltip_color', v)}
                />
              </Field>
              <Field label="粗细">
                <Select
                  value={ui.bubble_tooltip_font_weight}
                  onValueChange={v =>
                    patch('bubble_tooltip_font_weight', v as 'normal' | 'bold')
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="normal">常规</SelectItem>
                    <SelectItem value="bold">加粗</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
            </div>
            <ToggleField
              label="透明背景"
              hint="去掉招呼语的白底 / 边框 / 阴影，只留文字"
              checked={ui.bubble_tooltip_transparent}
              onChange={c => patch('bubble_tooltip_transparent', c)}
            />
            <ToggleField
              label="打开会话后隐藏"
              hint="点开面板时招呼语淡出"
              checked={ui.bubble_tooltip_dismiss_on_open}
              onChange={c => patch('bubble_tooltip_dismiss_on_open', c)}
            />
          </>
        ) : null}
        <ToggleField
          label="打开会话后保留浮窗"
          hint="默认保留；关闭后面板打开时浮窗按钮淡出"
          checked={ui.bubble_persist_when_open}
          onChange={c => patch('bubble_persist_when_open', c)}
        />
      </Section>

      <Section title="水印">
        <ToggleField
          label="显示水印"
          hint="面板底部一行小字（默认「powered by Chameleon」）"
          checked={ui.show_powered_by}
          onChange={c => patch('show_powered_by', c)}
        />
        {ui.show_powered_by ? (
          <Field label="水印文字" hint="纯文本；自由替换品牌名">
            <Input
              value={ui.powered_by_text}
              onChange={e => patch('powered_by_text', e.target.value)}
              placeholder="powered by Chameleon"
              maxLength={64}
            />
          </Field>
        ) : null}
      </Section>
    </div>
  );
};

const BubbleImagePicker: React.FC<{
  value: string | null;
  onChange: (next: string | null) => void;
}> = ({ value, onChange }) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const handleSelect = async (file: File) => {
    if (!file.type.startsWith('image/')) {
      toast.error('请选择图片文件');
      return;
    }
    if (file.size > 2 * 1024 * 1024) {
      toast.error('图片不能超过 2MB');
      return;
    }
    setUploading(true);
    try {
      const res = await uploadFile(file, { namespace: 'embed-bubble' });
      onChange(res.object_url);
    } catch (e) {
      toast.error(`上传失败：${(e as Error).message}`);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  return (
    <div className="flex items-center gap-3">
      <div className="flex h-14 w-14 items-center justify-center overflow-hidden rounded-full border border-stone-200 bg-stone-50">
        {value ? (
          <img src={value} alt="浮窗" className="h-full w-full object-cover" />
        ) : (
          <span className="text-[10px] text-stone-400">未上传</span>
        )}
      </div>
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-1.5">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={e => {
              const f = e.target.files?.[0];
              if (f) void handleSelect(f);
            }}
          />
          <Button
            size="sm"
            variant="outline"
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Upload className="mr-1 h-3.5 w-3.5" />
            )}
            {value ? '更换图片' : '上传图片'}
          </Button>
          {value && (
            <Button
              size="sm"
              variant="ghost"
              type="button"
              onClick={() => onChange(null)}
              title="移除，回退到纯色 + 内置 icon"
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
        <span className="text-[11px] text-stone-400">PNG / JPG / SVG，≤ 2MB；不传则用纯色 + icon</span>
      </div>
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
        <ToggleField
          label="回复后建议追问"
          hint="基于刚才一轮问答让 LLM 生成 3 个 follow-up 气泡（点击直接发送）"
          checked={v.show_followups}
          onChange={c => patch('show_followups', c)}
        />
      </Section>

      {v.allow_file_upload ? (
        <Section title="附件限制" hint="仅在允许附件上传时生效；后端会兜底再校一遍">
          <Field label="单文件大小上限" hint="超过会拒绝并提示用户">
            <NumberWithUnit
              value={v.max_file_size_mb}
              onChange={n => patch('max_file_size_mb', Math.max(1, Math.min(200, n)))}
              unit="MB"
              min={1}
              max={200}
              step={1}
            />
          </Field>
          <Field label="单条消息最多附件数">
            <NumberWithUnit
              value={v.max_files_per_message}
              onChange={n => patch('max_files_per_message', Math.max(1, Math.min(20, n)))}
              unit="个"
              min={1}
              max={20}
              step={1}
            />
          </Field>
          <Field label="允许的类型" hint="未勾选的类型会被 widget 端拒绝">
            <FileKindsPicker
              value={v.allowed_file_kinds}
              onChange={kinds => patch('allowed_file_kinds', kinds)}
            />
          </Field>
        </Section>
      ) : null}
    </div>
  );
};

const FILE_KIND_OPTIONS: { value: FileKind; label: string; hint: string }[] = [
  { value: 'image', label: '图片', hint: 'PNG/JPG/GIF/WEBP/SVG…' },
  { value: 'audio', label: '音频', hint: 'MP3/WAV/M4A…' },
  { value: 'document', label: '文档', hint: 'PDF/DOC/DOCX/PPTX/MD/TXT…' },
  { value: 'data', label: '数据表', hint: 'CSV/XLS/XLSX' },
];

const FileKindsPicker: React.FC<{
  value: FileKind[];
  onChange: (next: FileKind[]) => void;
}> = ({ value, onChange }) => {
  const toggle = (k: FileKind) => {
    const cur = new Set(value);
    if (cur.has(k)) cur.delete(k);
    else cur.add(k);
    // 至少保留一个，否则 widget 一刀切禁用附件
    if (cur.size === 0) return;
    onChange(FILE_KIND_OPTIONS.map(o => o.value).filter(v => cur.has(v)));
  };
  return (
    <div className="flex flex-wrap gap-1.5">
      {FILE_KIND_OPTIONS.map(opt => {
        const on = value.includes(opt.value);
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => toggle(opt.value)}
            title={opt.hint}
            className={`rounded-md border px-2.5 py-1 text-[12px] transition ${
              on
                ? 'border-blue-300 bg-blue-50 text-blue-700'
                : 'border-stone-200 bg-white text-stone-500 hover:border-stone-300'
            }`}
          >
            {opt.label}
          </button>
        );
      })}
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
const AccessTab: React.FC<{
  embedKey: string | null;
  identificationMode: IdentificationMode;
}> = ({ embedKey, identificationMode }) => {
  if (!embedKey) {
    return (
      <div className="rounded-lg border border-dashed border-stone-200 px-4 py-8 text-center text-[12.5px] text-stone-400">
        保存后可在此获取接入代码
      </div>
    );
  }
  const origin = window.location.origin;

  // 按身份模式拼 script —— anonymous 极简；其余加 data-* 占位 + 服务端示例
  const script =
    identificationMode === 'external_user_id'
      ? `<!-- 把 BIZ_USER_ID 替换为当前登录用户在你系统里的 ID -->\n<script\n  src="${origin}/widget.js"\n  data-embed-key="${embedKey}"\n  data-external-user-id="BIZ_USER_ID"\n  defer\n></script>`
      : identificationMode === 'signed_jwt'
        ? `<!-- 把 SIGNED_JWT 替换为你后端签发的 JWT；签发示例见下方 -->\n<script\n  src="${origin}/widget.js"\n  data-embed-key="${embedKey}"\n  data-jwt-token="SIGNED_JWT"\n  defer\n></script>`
        : `<script src="${origin}/widget.js" data-embed-key="${embedKey}" defer>\n</script>`;

  // iframe 同样按身份模式分支：external_user_id → ?euid=...，signed_jwt → ?jwt=...，
  // anonymous_device 保持极简（不带身份参数，widget 内自动用 localStorage device_id）
  const iframeStyle =
    'width:400px;height:600px;border:0;border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,.1)';
  const iframe =
    identificationMode === 'external_user_id'
      ? `<!-- 把 BIZ_USER_ID 替换为当前登录用户在你系统里的 ID -->\n<iframe\n  src="${origin}/embed/${embedKey}?euid=BIZ_USER_ID"\n  style="${iframeStyle}"\n></iframe>`
      : identificationMode === 'signed_jwt'
        ? `<!-- 把 SIGNED_JWT 替换为你后端签发的 JWT；签发示例见上方 -->\n<iframe\n  src="${origin}/embed/${embedKey}?jwt=SIGNED_JWT"\n  style="${iframeStyle}"\n></iframe>`
        : `<iframe src="${origin}/embed/${embedKey}" style="${iframeStyle}">\n</iframe>`;

  // 模式 2/3 给的接入提示
  const modeHint = MODE_HINTS[identificationMode];

  // 模式 3 额外：后端签 JWT 的 Python / Node 示例
  const pythonSignSnippet = `import jwt, time
SECRET = "<把后台「会话 tab → JWT 共享密钥」的值粘到这>"
token = jwt.encode(
    {"sub": "biz-user-12345", "exp": int(time.time()) + 3600},
    SECRET,
    algorithm="HS256",
)
# script：渲到 data-jwt-token 属性
# iframe：拼到 src 的 ?jwt= 参数（如 /embed/{key}?jwt={token}）`;
  const nodeSignSnippet = `import jwt from 'jsonwebtoken';
const SECRET = '<把后台「会话 tab → JWT 共享密钥」的值粘到这>';
const token = jwt.sign(
  { sub: 'biz-user-12345' },
  SECRET,
  { algorithm: 'HS256', expiresIn: '1h' },
);
// script：渲到 data-jwt-token 属性
// iframe：拼到 src 的 ?jwt= 参数（如 /embed/{key}?jwt=${token}）`;

  return (
    <div className="space-y-3">
      {modeHint ? (
        <div className="rounded-md border border-blue-100 bg-blue-50/60 px-3 py-2 text-[11.5px] leading-relaxed text-blue-800">
          {modeHint}
        </div>
      ) : null}
      <SnippetCard
        title="JS Widget"
        hint="推荐：右下角浮动气泡"
        code={script}
      />
      {identificationMode === 'signed_jwt' ? (
        <>
          <SnippetCard
            title="后端签 JWT · Python"
            hint="script: data-jwt-token / iframe: ?jwt="
            code={pythonSignSnippet}
          />
          <SnippetCard
            title="后端签 JWT · Node"
            hint="script: data-jwt-token / iframe: ?jwt="
            code={nodeSignSnippet}
          />
        </>
      ) : null}
      <SnippetCard title="iframe" hint="嵌入到页面内某个区域" code={iframe} />
    </div>
  );
};

const MODE_HINTS: Record<IdentificationMode, string | null> = {
  anonymous_device: null,
  external_user_id:
    '本应用配置为「外部用户 ID」模式：业务方网页（最好 SSR 渲染）把当前登录用户的 ID 注入 —— script 走 data-external-user-id 属性，iframe 走 ?euid= URL 参数；未注入时 widget 显错并禁用输入。',
  signed_jwt:
    '本应用配置为「签名 JWT」模式：业务方后端用「会话 tab」里录入的 HS256 密钥签 JWT（sub claim 当 end_user_id），把 token 注入 —— script 走 data-jwt-token 属性，iframe 走 ?jwt= URL 参数。',
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
      <div className="flex items-center justify-between bg-stone-100 px-3 py-1.5">
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
      <pre className="overflow-x-auto border-t border-slate-200 bg-slate-50 px-3 py-2.5 font-mono text-[11.5px] leading-relaxed text-slate-900 break-all whitespace-pre-wrap">
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

/** 生成 HS256 推荐密钥：32 字节随机 → base64url（无填充）。
 *  够强（256 bit 熵），可读字符可放 .env / data attr。 */
const generateHs256Secret = (): string => {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  // base64url（URL safe）
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
};

// ── S13b：会话策略 + owner key picker ────────────────────────

const IDENTIFICATION_MODE_OPTIONS: { value: IdentificationMode; label: string; desc: string }[] = [
  {
    value: 'anonymous_device',
    label: '匿名设备',
    desc: '浏览器持久化 device_id；同设备同浏览器视作同终端用户。无需接入方维护。',
  },
  {
    value: 'external_user_id',
    label: '外部 user id',
    desc: '接入方在颁 token 时直接传字符串 user_id（要保证前端无法篡改）。',
  },
  {
    value: 'signed_jwt',
    label: '签名 JWT',
    desc: '接入方后端 HS256 签名 JWT，后端用配置的密钥验签，sub claim 当 end_user_id。',
  },
];

interface AgentApiKeyLite {
  id: EntityId;
  name: string;
  key_prefix: string;
  revoked_at: string | null;
}

const SessionTab: React.FC<{
  agentId: string;
  policy: SessionPolicy;
  apiKeyId: EntityId | null;
  onPolicy: (v: SessionPolicy) => void;
  onApiKeyId: (v: EntityId | null) => void;
}> = ({ agentId, policy, apiKeyId, onPolicy, onApiKeyId }) => {
  const patch = <K extends keyof SessionPolicy>(key: K, value: SessionPolicy[K]) =>
    onPolicy({ ...policy, [key]: value });

  // owner key 候选：当前 agent 下未吊销的密钥
  const keysQ = useQuery({
    queryKey: ['agent-api-keys', agentId],
    queryFn: () => agentApi.listApiKeys(agentId),
    enabled: !!agentId,
  });
  const keyOptions = useMemo<AgentApiKeyLite[]>(
    () => (keysQ.data || []).filter(k => !k.revoked_at) as AgentApiKeyLite[],
    [keysQ.data],
  );

  return (
    <div className="space-y-4">
      {/* Owner key */}
      <section className="space-y-1.5">
        <Label>归属密钥（Owner Key）</Label>
        <Select
          value={apiKeyId != null ? String(apiKeyId) : '__none__'}
          onValueChange={v => onApiKeyId(v === '__none__' ? null : v)}
          disabled={!agentId}
        >
          <SelectTrigger>
            <SelectValue placeholder={agentId ? '选一个该应用的 API 密钥' : '请先在「基本」选择关联应用'} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">未绑定（流量归属仅靠 channel='embed'）</SelectItem>
            {keyOptions.map(k => (
              <SelectItem key={k.id} value={String(k.id)}>
                {k.name}
                <span className="ml-2 font-mono text-[10.5px] text-stone-500">{k.key_prefix}…</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="text-[11px] text-stone-500">
          嵌入式调用产生的 call_log 会冗余记录该 key，方便按 key 维度做计费/限流统计。
        </div>
      </section>

      <hr className="border-stone-200/70" />

      {/* Identification mode */}
      <section className="space-y-1.5">
        <Label>终端用户识别方式</Label>
        <Select
          value={policy.identification_mode}
          onValueChange={v => patch('identification_mode', v as IdentificationMode)}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {IDENTIFICATION_MODE_OPTIONS.map(o => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="text-[11px] text-stone-500">
          {
            IDENTIFICATION_MODE_OPTIONS.find(o => o.value === policy.identification_mode)?.desc
          }
        </div>
      </section>

      {policy.identification_mode === 'signed_jwt' ? (
        <section className="space-y-1.5">
          <Label>JWT 共享密钥（HS256）</Label>
          <div className="flex items-center gap-1.5">
            <Input
              type="text"
              value={policy.jwt_signing_secret_encrypted ?? ''}
              onChange={e =>
                patch('jwt_signing_secret_encrypted', e.target.value || null)
              }
              placeholder="点「生成」自动产出，或粘贴你已有的 HS256 密钥"
              className="font-mono text-[11.5px]"
            />
            <Button
              size="sm"
              variant="outline"
              type="button"
              onClick={() => patch('jwt_signing_secret_encrypted', generateHs256Secret())}
              title="随机生成 32 字节 base64url 密钥"
            >
              生成
            </Button>
            {policy.jwt_signing_secret_encrypted ? (
              <Button
                size="sm"
                variant="ghost"
                type="button"
                onClick={() => {
                  void navigator.clipboard.writeText(
                    policy.jwt_signing_secret_encrypted ?? '',
                  );
                  toast.success('密钥已复制');
                }}
                title="复制"
              >
                <Copy className="h-3.5 w-3.5" />
              </Button>
            ) : null}
          </div>
          <div className="text-[11px] text-amber-600">
            ⚠️ 复制保管好这串密钥，业务方后端用同一份签 JWT；保存后页面会用密文落库。
          </div>
        </section>
      ) : null}

      <hr className="border-stone-200/70" />

      {/* widget 行为 */}
      <section className="space-y-2.5">
        <Label>widget 会话行为</Label>
        <ToggleRow
          label="显示历史会话侧栏"
          desc="widget 左侧列出该终端用户的过往会话"
          checked={policy.show_history_sidebar}
          onChange={v => patch('show_history_sidebar', v)}
        />
        <ToggleRow
          label="自动续接上次会话"
          desc="加载 widget 时优先打开 localStorage 里的上次会话；关 = 永远新开"
          checked={policy.auto_resume_last}
          onChange={v => patch('auto_resume_last', v)}
        />
        <ToggleRow
          label="允许用户自管理会话"
          desc="允许终端用户删除 / 重命名自己的会话；关 = 删/改名端点拒绝"
          checked={policy.allow_user_manage}
          onChange={v => patch('allow_user_manage', v)}
        />
      </section>

      <hr className="border-stone-200/70" />

      <section className="space-y-1.5">
        <Label>历史会话时间窗（天）</Label>
        <Input
          type="number"
          min={1}
          max={365}
          value={policy.max_history_days}
          onChange={e =>
            patch('max_history_days', Math.max(1, Math.min(365, Number(e.target.value) || 90)))
          }
          className="max-w-[180px]"
        />
        <div className="text-[11px] text-stone-500">
          列表只展示该时间窗内活跃的会话；不影响 DB 留存。
        </div>
      </section>
    </div>
  );
};

const ToggleRow: React.FC<{
  label: string;
  desc: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}> = ({ label, desc, checked, onChange }) => (
  <div className="flex items-start justify-between gap-3 rounded-md border border-stone-200/70 bg-white px-3 py-2.5">
    <div className="min-w-0 flex-1">
      <div className="text-[12.5px] font-medium text-stone-800">{label}</div>
      <div className="mt-0.5 text-[11px] text-stone-500">{desc}</div>
    </div>
    <Switch checked={checked} onCheckedChange={onChange} className="shrink-0 self-start" />
  </div>
);
