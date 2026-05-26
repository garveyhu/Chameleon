/** /kbs/:id/chunking-preview —— 三栏 chunking 实时预览
 *
 * 左：原文 textarea（可粘贴 / 留空时用默认示例）
 * 中：chunks 卡片列表（按 seq 渲染，hover 显 token / char count；点击高亮）
 * 右：strategy 表单（复用现有 kb-config-form 的字段；只在 preview 内部状态变化）
 *
 * 不写 DB —— 调 chunkingPreview() 拿结果即返。
 */
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { useMutation, useQuery } from '@tanstack/react-query';
import { ChevronLeft, RotateCw, Sparkles } from 'lucide-react';

import { Spinner } from '@/core/components/common/spinner';
import { SectionCard } from '@/core/components/table';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { Switch } from '@/core/components/ui/switch';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import { formatNumber } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import { kbApi } from '@/system/kbs/services/kb';
import type { ChunkingPreviewItem } from '@/system/kbs/services/kb';
import type { KbChunkMode, KbChunkStrategy } from '@/system/kbs/types/kb';

const DEFAULT_TEXT = `Chameleon 是一个多 provider AI Agent 聚合平台。

它把 Dify 的可视化编排、LobeChat 的颜值、LangFuse 的观测、FastGPT 的 RAG、One-API 的网关能力缝合在一个 OSS 项目里。

调用方按 model_code 路由到 channel，失败自动 failover，trace 嵌套 observation 串到 call_logs。

工作流（GraphEngine）支持 LLM / KB / Tool / If-Else / End 五类节点；test-run 与持久化 Run 双轨；
trace tree drawer 直接复用 P17.C1 的可视化。`;

const MODES: { value: KbChunkMode; label: string }[] = [
  { value: 'fixed', label: '固定字数' },
  { value: 'paragraph', label: '按段落' },
  { value: 'sentence', label: '按句子' },
  { value: 'regex', label: '自定义正则' },
  { value: 'token', label: '按 Token' },
  { value: 'parent_child', label: '父子分层' },
];

export const KbChunkingPreviewPage = () => {
  const { id } = useParams<{ id: string }>();
  const kbId = id ?? '';
  const nav = useNavigate();

  const kbQ = useQuery({
    queryKey: ['kb', kbId],
    queryFn: () => kbApi.get(kbId),
    enabled: !!kbId,
  });

  const [text, setText] = useState(DEFAULT_TEXT);
  const [strategy, setStrategy] = useState<KbChunkStrategy>({
    mode: 'fixed',
    chunk_size: 200,
    overlap: 30,
  });
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);

  // 初次载入：用 KB 的 strategy（更直观）——合法的服务端→本地态同步
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (kbQ.data?.chunk_strategy) setStrategy(kbQ.data.chunk_strategy);
  }, [kbQ.data]);

  const previewMut = useMutation({
    mutationFn: () => kbApi.chunkingPreview({ text, strategy }),
    onError: e => toast.error(`预览失败：${(e as Error).message}`),
  });

  // 切策略 / 文本变化时延迟自动跑预览（300ms 防抖）
  useEffect(() => {
    const tid = setTimeout(() => {
      if (text.trim()) previewMut.mutate();
    }, 300);
    return () => clearTimeout(tid);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, JSON.stringify(strategy)]);

  if (kbQ.isLoading || !kbQ.data) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    );
  }

  const result = previewMut.data;

  return (
    <SectionCard className="!p-0">
      <header className="flex items-center justify-between border-b border-stone-200/70 px-3 py-2">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => nav(`/kbs/${kbId}`)}>
            <ChevronLeft className="mr-0.5 h-3.5 w-3.5" />
            返回
          </Button>
          <div>
            <h2 className="text-[14px] font-medium text-stone-900">切块策略预览</h2>
            <div className="text-[11px] text-stone-500">KB「{kbQ.data.name}」· 不写库；调试用</div>
          </div>
        </div>
        <div className="flex items-center gap-2 text-[11.5px] text-stone-500">
          {result && (
            <>
              <span>
                <span className="font-medium text-stone-700">{result.count}</span> chunks
              </span>
              <span className="text-stone-300">·</span>
              <span>mode={result.mode}</span>
            </>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => previewMut.mutate()}
            disabled={previewMut.isPending}
          >
            <RotateCw className={cn('mr-1 h-3 w-3', previewMut.isPending && 'animate-spin')} />
            重跑
          </Button>
        </div>
      </header>

      <div className="grid h-[calc(100vh-180px)] min-h-[480px] grid-cols-[1fr_1.2fr_320px]">
        {/* 左：原文 */}
        <div className="flex flex-col border-r border-stone-200/70">
          <div className="bg-warm-2/40 border-b border-stone-200/70 px-3 py-1.5 text-[10.5px] tracking-wider text-stone-500 uppercase">
            原文（{text.length} 字符）
          </div>
          <Textarea
            value={text}
            onChange={e => setText(e.target.value)}
            className="min-h-0 flex-1 resize-none rounded-none border-0 font-mono text-[12px] leading-relaxed"
            placeholder="粘贴一段文本，或保留默认示例"
          />
        </div>

        {/* 中：chunks 卡片 */}
        <div className="bg-warm-2/20 flex flex-col border-r border-stone-200/70">
          <div className="bg-warm-2/40 border-b border-stone-200/70 px-3 py-1.5 text-[10.5px] tracking-wider text-stone-500 uppercase">
            Chunks
          </div>
          <div className="flex-1 overflow-y-auto p-3">
            {previewMut.isPending && !result ? (
              <div className="py-10 text-center text-[12px] text-stone-400">生成中…</div>
            ) : !result || result.count === 0 ? (
              <div className="py-10 text-center text-[12px] text-stone-400">
                {text.trim() ? '无切块' : '请输入原文'}
              </div>
            ) : (
              <div className="space-y-2">
                {result.chunks.map(c => (
                  <ChunkCard
                    key={c.seq}
                    chunk={c}
                    selected={selectedSeq === c.seq}
                    onClick={() => setSelectedSeq(c.seq === selectedSeq ? null : c.seq)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* 右：strategy */}
        <div className="bg-warm-2/40 flex flex-col">
          <div className="bg-warm-2/40 border-b border-stone-200/70 px-3 py-1.5 text-[10.5px] tracking-wider text-stone-500 uppercase">
            策略
          </div>
          <div className="space-y-3 overflow-y-auto p-3">
            <Field label="mode">
              <div className="grid grid-cols-2 gap-1.5">
                {MODES.map(m => (
                  <button
                    key={m.value}
                    type="button"
                    onClick={() => setStrategy(s => ({ ...s, mode: m.value }))}
                    className={cn(
                      'rounded-md border px-2 py-1.5 text-[11.5px] transition',
                      strategy.mode === m.value
                        ? 'border-amber-400 bg-amber-50/60 text-amber-800'
                        : 'border-stone-200 bg-white text-stone-600 hover:border-stone-300',
                    )}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
            </Field>

            <Field
              label={`chunk_size = ${strategy.chunk_size ?? (strategy.mode === 'token' ? 512 : 800)} ${
                strategy.mode === 'token' ? 'token' : '字符'
              }`}
            >
              <input
                type="range"
                min={strategy.mode === 'token' ? 64 : 50}
                max={strategy.mode === 'token' ? 2000 : 4000}
                step={strategy.mode === 'token' ? 32 : 50}
                value={strategy.chunk_size ?? (strategy.mode === 'token' ? 512 : 800)}
                onChange={e => setStrategy(s => ({ ...s, chunk_size: Number(e.target.value) }))}
                className="w-full accent-amber-600"
              />
            </Field>

            <Field
              label={`overlap = ${strategy.overlap ?? (strategy.mode === 'token' ? 50 : 100)} ${
                strategy.mode === 'token' ? 'token' : '字符'
              }`}
            >
              <input
                type="range"
                min={0}
                max={strategy.mode === 'token' ? 300 : 500}
                step={strategy.mode === 'token' ? 8 : 10}
                value={strategy.overlap ?? (strategy.mode === 'token' ? 50 : 100)}
                onChange={e => setStrategy(s => ({ ...s, overlap: Number(e.target.value) }))}
                className="w-full accent-amber-600"
              />
            </Field>

            {strategy.mode === 'regex' && (
              <Field label="separator_regex">
                <Input
                  value={strategy.separator_regex ?? ''}
                  onChange={e => setStrategy(s => ({ ...s, separator_regex: e.target.value }))}
                  placeholder="\\n\\n+"
                  className="h-7 font-mono text-[11.5px]"
                />
              </Field>
            )}

            {strategy.mode === 'token' && (
              <Field label="模型编码器 (model)">
                <Input
                  value={strategy.model ?? ''}
                  onChange={e => setStrategy(s => ({ ...s, model: e.target.value || undefined }))}
                  placeholder="留空走 cl100k_base"
                  className="h-7 font-mono text-[11.5px]"
                />
              </Field>
            )}

            {strategy.mode === 'parent_child' && (
              <Field label={`parent 大块上限 = ${strategy.parent_size ?? 1024} 字符`}>
                <input
                  type="range"
                  min={512}
                  max={4000}
                  step={128}
                  value={strategy.parent_size ?? 1024}
                  onChange={e => setStrategy(s => ({ ...s, parent_size: Number(e.target.value) }))}
                  className="w-full accent-amber-600"
                />
                <div className="mt-1 text-[10.5px] leading-snug text-stone-500">
                  预览显示 child 小块；chunk_size 即 child 大小。
                </div>
              </Field>
            )}

            <Field label="文本清洗">
              <div className="space-y-1.5">
                <CleanRow
                  label="规范化空白"
                  checked={!!strategy.clean?.whitespace}
                  onChange={v => setStrategy(s => ({ ...s, clean: { ...s.clean, whitespace: v } }))}
                />
                <CleanRow
                  label="删除 URL / 邮箱"
                  checked={!!strategy.clean?.urls_emails}
                  onChange={v =>
                    setStrategy(s => ({ ...s, clean: { ...s.clean, urls_emails: v } }))
                  }
                />
              </div>
            </Field>

            <div className="border-t border-stone-200 pt-2 text-[10.5px] leading-snug text-stone-500">
              <Sparkles className="mr-1 inline h-3 w-3 text-amber-500" />
              修改即时预览（300ms 防抖）；不会改 KB 的策略，需到「配置」tab 保存。
            </div>
          </div>
        </div>
      </div>
    </SectionCard>
  );
};

const ChunkCard = ({
  chunk,
  selected,
  onClick,
}: {
  chunk: ChunkingPreviewItem;
  selected: boolean;
  onClick: () => void;
}) => (
  <button
    type="button"
    onClick={onClick}
    className={cn(
      'w-full rounded-md border bg-white px-3 py-2 text-left transition',
      selected
        ? 'border-amber-400 ring-2 ring-amber-100'
        : 'border-stone-200 hover:border-stone-300 hover:bg-stone-50',
    )}
  >
    <div className="flex items-center justify-between text-[10px] tracking-wider text-stone-500 uppercase">
      <span className="font-mono">#{chunk.seq}</span>
      <span className="tnum font-mono">
        {formatNumber(chunk.char_count)} 字 · ~{formatNumber(chunk.token_count_approx)} tok
      </span>
    </div>
    <div className="mt-1 text-[12px] break-words whitespace-pre-wrap text-stone-800">
      {chunk.content}
    </div>
  </button>
);

const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div>
    <label className="mb-1 block text-[11.5px] text-stone-700">{label}</label>
    {children}
  </div>
);

const CleanRow = ({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) => (
  <label className="flex cursor-pointer items-center justify-between rounded-md border border-stone-200 bg-white px-2.5 py-1.5 text-[11.5px] text-stone-600">
    {label}
    <Switch checked={checked} onCheckedChange={onChange} />
  </label>
);
