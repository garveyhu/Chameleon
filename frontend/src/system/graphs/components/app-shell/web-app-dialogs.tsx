/** Web App 配置弹窗 —— 外观 / 行为 两页 + 右侧实时预览
 *
 * 全部在编辑器内完成，不跳系统页面。公开聊天页为 /embed/{embed_key}。
 * 开场白 / 建议问题由「开始节点」单一拥有（ensure 时回灌），这里只读展示，
 * 去编排里改；其余外观/行为字段写回 embed_config（graph /web-app/update）。
 * 嵌入式应用（<script> bubble widget）的接入代码见 EmbedAppModal。
 */
import { useState } from 'react';

import { Check, Code2, Copy, ExternalLink, MessageSquare, Palette } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

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
import { Switch } from '@/core/components/ui/switch';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import type { WebAppInfo } from '@/system/graphs/types/graph';

export type WebAppTab = 'appearance' | 'behavior';

const TABS: { key: WebAppTab; label: string; icon: LucideIcon }[] = [
  { key: 'appearance', label: '外观', icon: Palette },
  { key: 'behavior', label: '行为', icon: MessageSquare },
];

interface SavePayload {
  name: string;
  description: string;
  ui_config: Record<string, unknown>;
  behavior: Record<string, unknown>;
}

interface Props {
  open: boolean;
  onClose: () => void;
  info: WebAppInfo;
  onSave: (payload: SavePayload) => void;
  saving: boolean;
  initialTab?: WebAppTab;
}

export const WebAppDialog = ({ open, onClose, info, onSave, saving, initialTab }: Props) => {
  const [tab, setTab] = useState<WebAppTab>(initialTab ?? 'appearance');

  const [name, setName] = useState(info.name);
  const [color, setColor] = useState((info.ui_config.primary_color as string) || '#6366f1');
  const [emoji, setEmoji] = useState((info.ui_config.icon_emoji as string) || '');
  const [title, setTitle] = useState((info.ui_config.title as string) || '');
  const [subtitle, setSubtitle] = useState((info.ui_config.subtitle as string) || '');
  const [placeholder, setPlaceholder] = useState((info.behavior.placeholder as string) || '');
  const [showFeedback, setShowFeedback] = useState(info.behavior.show_feedback !== false);

  // start 节点拥有，只读
  const opener = (info.behavior.welcome_message as string) || '';
  const suggested = (info.behavior.suggested_questions as string[]) || [];

  const submit = () =>
    onSave({
      name: name.trim() || info.name,
      description: subtitle,
      ui_config: {
        ...info.ui_config,
        primary_color: color,
        icon_emoji: emoji || undefined,
        title: title || undefined,
        subtitle: subtitle || undefined,
      },
      behavior: {
        ...info.behavior,
        placeholder: placeholder || undefined,
        show_feedback: showFeedback,
      },
    });

  const previewTitle = title || name || 'Chameleon 助手';

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="xl" className="w-[920px] max-w-[95vw]">
        <ModalHeader>
          <ModalTitle className="flex items-center gap-2">
            Web App 配置
            <span className="font-mono text-[11px] font-normal text-stone-400">
              {info.embed_key}
            </span>
          </ModalTitle>
        </ModalHeader>
        <ModalBody className="!p-0">
          <div className="flex h-[520px]">
            {/* tab nav */}
            <nav className="bg-warm-2/30 w-28 shrink-0 border-r border-stone-200/70 p-2">
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
                  <t.icon className="h-3.5 w-3.5" strokeWidth={1.75} />
                  {t.label}
                </button>
              ))}
            </nav>

            {/* 表单区 */}
            <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
              {tab === 'appearance' && (
                <>
                  <Field label="应用名称">
                    <Input value={name} onChange={e => setName(e.target.value)} className="h-8" />
                  </Field>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="主题色">
                      <div className="flex items-center gap-2">
                        <input
                          type="color"
                          value={color}
                          onChange={e => setColor(e.target.value)}
                          className="h-8 w-10 cursor-pointer rounded border border-stone-200 bg-white"
                        />
                        <Input
                          value={color}
                          onChange={e => setColor(e.target.value)}
                          className="h-8 flex-1 font-mono text-[12px]"
                        />
                      </div>
                    </Field>
                    <Field label="头像 emoji（留空用默认图标）">
                      <Input
                        value={emoji}
                        onChange={e => setEmoji(e.target.value.slice(0, 4))}
                        placeholder="🤖"
                        className="h-8"
                      />
                    </Field>
                  </div>
                  <Field label="标题">
                    <Input
                      value={title}
                      onChange={e => setTitle(e.target.value)}
                      placeholder={name}
                      className="h-8"
                    />
                  </Field>
                  <Field label="副标题">
                    <Input
                      value={subtitle}
                      onChange={e => setSubtitle(e.target.value)}
                      placeholder="一句话介绍这个助手"
                      className="h-8"
                    />
                  </Field>
                  <Field label="输入框占位符">
                    <Input
                      value={placeholder}
                      onChange={e => setPlaceholder(e.target.value)}
                      placeholder="输入消息……"
                      className="h-8"
                    />
                  </Field>
                </>
              )}

              {tab === 'behavior' && (
                <>
                  <ToggleField
                    label="显示消息操作"
                    hint="在回答下方显示复制 / 朗读等操作"
                    checked={showFeedback}
                    onChange={setShowFeedback}
                  />
                  <ReadOnlyField label="开场白" hint="由「开始节点」配置，去编排里修改">
                    {opener ? (
                      <div className="rounded-md border border-stone-200 bg-stone-50 px-2.5 py-2 text-[12.5px] whitespace-pre-wrap text-stone-700">
                        {opener}
                      </div>
                    ) : (
                      <Empty>未设置（开始节点未配置开场白）</Empty>
                    )}
                  </ReadOnlyField>
                  <ReadOnlyField label="建议问题" hint="由「开始节点」配置，去编排里修改">
                    {suggested.length ? (
                      <div className="flex flex-wrap gap-1.5">
                        {suggested.map((q, i) => (
                          <span
                            key={i}
                            className="rounded-full border border-stone-200 bg-white px-2.5 py-1 text-[11.5px] text-stone-600"
                          >
                            {q}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <Empty>未设置</Empty>
                    )}
                  </ReadOnlyField>
                </>
              )}
            </div>

            {/* 实时预览 */}
            <div className="w-[300px] shrink-0 border-l border-stone-200/70 bg-stone-100/60 p-4">
              <Preview
                color={color}
                emoji={emoji}
                title={previewTitle}
                subtitle={subtitle}
                opener={opener}
                suggested={suggested}
                placeholder={placeholder || '输入消息……'}
              />
            </div>
          </div>
        </ModalBody>
        <ModalFooter>
          <Button onClick={submit} disabled={saving}>
            {saving ? '保存中…' : '保存'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

// ── 嵌入式应用（<script> bubble widget + iframe）────────────

const CodeBlock = ({ code }: { code: string }) => {
  const { copied, copy } = useCopy();
  return (
    <div className="group relative">
      <pre className="overflow-x-auto rounded-lg bg-stone-900 px-3.5 py-3 font-mono text-[12px] leading-relaxed whitespace-pre-wrap text-stone-100">
        {code}
      </pre>
      <button
        type="button"
        onClick={() => copy(code)}
        title="复制"
        className="absolute top-2 right-2 rounded p-1 text-stone-400 transition hover:bg-stone-700 hover:text-stone-100"
      >
        {copied ? (
          <Check className="h-3.5 w-3.5 text-emerald-400" />
        ) : (
          <Copy className="h-3.5 w-3.5" />
        )}
      </button>
    </div>
  );
};

export const EmbedAppModal = ({
  open,
  onClose,
  embedKey,
}: {
  open: boolean;
  onClose: () => void;
  embedKey: string;
}) => {
  const origin = window.location.origin;
  const url = `${origin}/embed/${embedKey}`;
  const script = `<script
  src="${origin}/widget.js"
  data-embed-key="${embedKey}"
  defer>
</script>`;
  const iframe = `<iframe
  src="${url}"
  style="width: 100%; height: 100%; min-height: 640px; border: 0;"
  allow="microphone">
</iframe>`;

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="lg">
        <ModalHeader>
          <ModalTitle className="flex items-center gap-2">
            <Code2 className="h-4 w-4 text-stone-500" />
            嵌入式应用
          </ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          <Field label="悬浮气泡（推荐）—— 把这段脚本贴到网站 </body> 前">
            <CodeBlock code={script} />
            <p className="mt-1.5 text-[11px] text-stone-400">
              访客页面右下角出现可点开的对话气泡；外观 / 开场白在「设置」里配置。
            </p>
          </Field>
          <Field label="整页内嵌 —— 用 iframe 嵌到目标容器">
            <CodeBlock code={iframe} />
          </Field>
          <Field label="公开访问 URL">
            <div className="flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded-md border border-stone-200 bg-stone-50 px-2 py-1.5 font-mono text-[12px] text-stone-700">
                {url}
              </code>
              <Button size="sm" variant="outline" onClick={() => window.open(url, '_blank')}>
                <ExternalLink className="h-3 w-3" />
              </Button>
            </div>
          </Field>
        </ModalBody>
      </ModalContent>
    </Modal>
  );
};

// ── 预览 ───────────────────────────────────────────────────

const Preview = ({
  color,
  emoji,
  title,
  subtitle,
  opener,
  suggested,
  placeholder,
}: {
  color: string;
  emoji: string;
  title: string;
  subtitle: string;
  opener: string;
  suggested: string[];
  placeholder: string;
}) => (
  <div className="flex h-full flex-col overflow-hidden rounded-xl border border-stone-200 bg-stone-50 shadow-sm">
    <div className="flex items-center gap-2 border-b border-stone-200 bg-white px-3 py-2">
      <span
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[14px] text-white"
        style={{ background: color }}
      >
        {emoji || '🤖'}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[12px] font-semibold text-stone-900">{title}</div>
        {subtitle && <div className="truncate text-[10px] text-stone-500">{subtitle}</div>}
      </div>
    </div>
    <div className="flex-1 space-y-2 overflow-hidden p-3">
      <div className="flex items-start gap-1.5">
        <span
          className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded text-[10px] text-white"
          style={{ background: color }}
        >
          {emoji || '🤖'}
        </span>
        <div className="rounded-xl rounded-tl-sm border border-stone-200 bg-white px-2.5 py-1.5 text-[11px] text-stone-700 shadow-sm">
          {opener || '你好！有什么可以帮你的？'}
        </div>
      </div>
      {suggested.slice(0, 3).map((q, i) => (
        <div
          key={i}
          className="ml-6 inline-block rounded-full border px-2 py-0.5 text-[10px]"
          style={{ borderColor: color, color }}
        >
          {q}
        </div>
      ))}
    </div>
    <div className="border-t border-stone-200 bg-white p-2">
      <div className="flex items-center gap-1.5 rounded-lg border border-stone-200 px-2 py-1.5">
        <span className="flex-1 truncate text-[10.5px] text-stone-400">{placeholder}</span>
        <span
          className="flex h-5 w-5 items-center justify-center rounded-md text-white"
          style={{ background: color }}
        >
          <svg viewBox="0 0 24 24" className="h-3 w-3 fill-current">
            <path d="M2 21l21-9L2 3v7l15 2-15 2z" />
          </svg>
        </span>
      </div>
    </div>
  </div>
);

// ── 小组件 ─────────────────────────────────────────────────

const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div>
    <label className="mb-1 block text-[12px] text-stone-600">{label}</label>
    {children}
  </div>
);

const ReadOnlyField = ({
  label,
  hint,
  children,
}: {
  label: string;
  hint: string;
  children: React.ReactNode;
}) => (
  <div>
    <div className="mb-1 flex items-center gap-2">
      <label className="text-[12px] text-stone-600">{label}</label>
      <span className="text-[10.5px] text-stone-400">{hint}</span>
    </div>
    {children}
  </div>
);

const ToggleField = ({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) => (
  <div className="flex items-center justify-between rounded-md border border-stone-200 px-3 py-2">
    <div>
      <div className="text-[12.5px] text-stone-800">{label}</div>
      <div className="text-[10.5px] text-stone-400">{hint}</div>
    </div>
    <Switch checked={checked} onCheckedChange={onChange} />
  </div>
);

const Empty = ({ children }: { children: React.ReactNode }) => (
  <div className="rounded-md border border-dashed border-stone-200 px-2.5 py-2 text-[11.5px] text-stone-400">
    {children}
  </div>
);

const useCopy = () => {
  const [copied, setCopied] = useState(false);
  const copy = (text: string) => {
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      toast.success('已复制');
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return { copied, copy };
};
