/** 知识库创建向导（Dify 式多步）—— 创建与首次导入合一。
 *
 * 步骤：① 基本信息 + 数据源（上传文件 / 粘贴文本）→ ② 分段与检索设置 →
 *       ③ 确认并创建（建库 → 导入文件/文本 → 跳详情，余下 ingest 异步进行）。
 *
 * v1 取舍：embedding 走系统默认单维；数据源先支持文件 + 文本（Notion/爬取/URL 后期）。
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useMutation } from '@tanstack/react-query';
import { ArrowLeft, Check, FileText, Trash2, UploadCloud } from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { Label } from '@/core/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import { documentApi } from '@/system/kbs/services/document';
import { kbApi } from '@/system/kbs/services/kb';
import type { KbChunkStrategy } from '@/system/kbs/types/kb';

type ChunkMode = 'fixed' | 'paragraph' | 'sentence' | 'regex' | 'token';
type RecallMode = 'vector' | 'hybrid' | 'keyword';

const STEPS = ['基本信息 · 数据源', '分段与检索', '确认并创建'];

const CHUNK_MODES: { value: ChunkMode; label: string }[] = [
  { value: 'fixed', label: '定长切分' },
  { value: 'paragraph', label: '按段落' },
  { value: 'sentence', label: '按句子' },
  { value: 'regex', label: '正则分隔' },
  { value: 'token', label: '按 Token' },
];

const RECALL_MODES: { value: RecallMode; label: string; desc: string }[] = [
  { value: 'vector', label: '向量检索', desc: '语义相似，泛化强' },
  { value: 'hybrid', label: '混合检索', desc: '向量 + 关键词，推荐' },
  { value: 'keyword', label: '关键词检索', desc: 'BM25，精确命中术语' },
];

const slugify = (s: string) =>
  s
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64);

export const KbCreatePage = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);

  // ① 基本信息 + 数据源
  const [name, setName] = useState('');
  const [kbKey, setKbKey] = useState('');
  const [kbKeyTouched, setKbKeyTouched] = useState(false);
  const [description, setDescription] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [pastedText, setPastedText] = useState('');
  // 中文名 slug 为空时的稳定兜底 key（一次生成，可编辑）
  const [autoKey] = useState(() => `kb-${Math.random().toString(36).slice(2, 8)}`);

  // ② 分段与检索
  const [mode, setMode] = useState<ChunkMode>('fixed');
  const [chunkSize, setChunkSize] = useState(800);
  const [overlap, setOverlap] = useState(100);
  const [separator, setSeparator] = useState('\\n\\n');
  const [recallMode, setRecallMode] = useState<RecallMode>('hybrid');
  const [topK, setTopK] = useState(5);

  const effectiveKey = kbKeyTouched ? kbKey : slugify(name) || autoKey;

  const createMut = useMutation({
    mutationFn: async () => {
      const strategy: KbChunkStrategy = {
        mode,
        chunk_size: chunkSize,
        overlap,
        ...(mode === 'regex' ? { separator_regex: separator } : {}),
      };
      const kb = await kbApi.create({
        kb_key: effectiveKey,
        name,
        description: description || undefined,
        chunk_size: chunkSize,
        chunk_overlap: overlap,
        chunk_strategy: strategy,
      });
      // 检索默认（recall_mode / top_k）走 update（创建接口未含）
      await kbApi.update(kb.id, { recall_mode: recallMode, default_top_k: topK });
      // 首次导入：文件 + 粘贴文本（ingest 异步进行）
      if (files.length) await documentApi.upload(kb.id, files);
      if (pastedText.trim()) {
        await documentApi.fromText(kb.id, `${name} - 文本`, pastedText.trim());
      }
      return kb;
    },
    onSuccess: kb => {
      toast.success('知识库已创建，文档正在后台解析');
      navigate(`/kbs/${kb.id}`);
    },
    onError: e => toast.error(`创建失败：${(e as Error).message}`),
  });

  const canNext0 = !!name.trim() && !!effectiveKey;

  return (
    <div className="mx-auto max-w-3xl px-4 py-2">
      {/* 头部 + 步骤条 */}
      <div className="mb-5 flex items-center gap-3">
        <button
          type="button"
          onClick={() => navigate('/kbs')}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12.5px] text-stone-500 hover:bg-stone-100 hover:text-stone-800"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> 知识库
        </button>
        <span className="text-stone-300">/</span>
        <span className="text-[15px] font-medium text-stone-900">创建知识库</span>
      </div>

      <div className="mb-6 flex items-center gap-2">
        {STEPS.map((label, i) => (
          <div key={label} className="flex flex-1 items-center gap-2">
            <div
              className={cn(
                'flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-medium',
                i < step
                  ? 'bg-blue-600 text-white'
                  : i === step
                    ? 'bg-blue-600 text-white'
                    : 'bg-stone-200 text-stone-500',
              )}
            >
              {i < step ? <Check className="h-3.5 w-3.5" /> : i + 1}
            </div>
            <span
              className={cn(
                'text-[12.5px]',
                i === step ? 'font-medium text-stone-900' : 'text-stone-500',
              )}
            >
              {label}
            </span>
            {i < STEPS.length - 1 && <div className="h-px flex-1 bg-stone-200" />}
          </div>
        ))}
      </div>

      {/* 步骤内容 */}
      <div className="rounded-xl border border-stone-200/70 bg-white p-5">
        {step === 0 && (
          <div className="space-y-4">
            <Field label="名称" required>
              <Input
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="如：产品 FAQ"
              />
            </Field>
            <Field label="标识 (kb_key)" hint="字母/数字/_-，全局唯一；留空按名称生成">
              <Input
                value={effectiveKey}
                onChange={e => {
                  setKbKeyTouched(true);
                  setKbKey(e.target.value);
                }}
                className="font-mono"
                placeholder="product-faq"
              />
            </Field>
            <Field label="描述">
              <Textarea
                value={description}
                onChange={e => setDescription(e.target.value)}
                rows={2}
                placeholder="选填，便于团队识别"
              />
            </Field>

            <div className="border-t border-stone-200/60 pt-4">
              <div className="mb-2 text-[12.5px] font-medium text-stone-700">
                数据源{' '}
                <span className="font-normal text-stone-400">· 选填，建好后也能继续添加</span>
              </div>
              <FileDrop files={files} onChange={setFiles} />
              <div className="mt-3">
                <Label className="text-[11.5px] text-stone-500">或粘贴文本</Label>
                <Textarea
                  value={pastedText}
                  onChange={e => setPastedText(e.target.value)}
                  rows={4}
                  placeholder="直接粘贴一段文本作为首个文档"
                  className="mt-1"
                />
              </div>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-5">
            <div>
              <div className="mb-2 text-[12.5px] font-medium text-stone-700">分段方式</div>
              <div className="grid grid-cols-3 gap-2">
                <div className="col-span-3">
                  <Select value={mode} onValueChange={v => setMode(v as ChunkMode)}>
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {CHUNK_MODES.map(m => (
                        <SelectItem key={m.value} value={m.value}>
                          {m.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <Field label="块大小">
                  <Input
                    type="number"
                    value={chunkSize}
                    onChange={e => setChunkSize(Number(e.target.value))}
                  />
                </Field>
                <Field label="重叠">
                  <Input
                    type="number"
                    value={overlap}
                    onChange={e => setOverlap(Number(e.target.value))}
                  />
                </Field>
                {mode === 'regex' && (
                  <Field label="正则分隔">
                    <Input
                      value={separator}
                      onChange={e => setSeparator(e.target.value)}
                      className="font-mono"
                    />
                  </Field>
                )}
              </div>
              <p className="mt-1.5 text-[11px] text-stone-400">
                建好后可在「分段预览」里精调，更复杂的分层 / QA 分块后续版本支持。
              </p>
            </div>

            <div className="border-t border-stone-200/60 pt-4">
              <div className="mb-2 text-[12.5px] font-medium text-stone-700">检索设置</div>
              <div className="grid grid-cols-3 gap-2">
                {RECALL_MODES.map(r => (
                  <button
                    key={r.value}
                    type="button"
                    onClick={() => setRecallMode(r.value)}
                    className={cn(
                      'rounded-lg border px-3 py-2.5 text-left transition',
                      recallMode === r.value
                        ? 'border-blue-400 bg-blue-50/60'
                        : 'border-stone-200 hover:border-stone-300',
                    )}
                  >
                    <div className="text-[12.5px] font-medium text-stone-800">{r.label}</div>
                    <div className="mt-0.5 text-[11px] text-stone-500">{r.desc}</div>
                  </button>
                ))}
              </div>
              <div className="mt-3 w-40">
                <Field label="召回数 top_k">
                  <Input
                    type="number"
                    value={topK}
                    onChange={e => setTopK(Number(e.target.value))}
                  />
                </Field>
              </div>
              <p className="mt-1.5 text-[11px] text-stone-400">
                Embedding 走系统默认模型（v1 全局单维）。
              </p>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-3 text-[12.5px]">
            <Row k="名称" v={name} />
            <Row k="标识" v={effectiveKey} mono />
            <Row
              k="分段"
              v={`${CHUNK_MODES.find(m => m.value === mode)?.label} · 块 ${chunkSize} / 重叠 ${overlap}`}
            />
            <Row
              k="检索"
              v={`${RECALL_MODES.find(r => r.value === recallMode)?.label} · top_k ${topK}`}
            />
            <Row
              k="首次导入"
              v={
                files.length || pastedText.trim()
                  ? `${files.length} 个文件${pastedText.trim() ? ' + 1 段文本' : ''}`
                  : '无（建好后再加）'
              }
            />
            <p className="pt-1 text-[11px] text-stone-400">
              点击创建后立即建库并开始解析文档；解析在后台进行，可在详情页查看进度。
            </p>
          </div>
        )}
      </div>

      {/* 底部导航 */}
      <div className="mt-4 flex items-center justify-between">
        <Button
          variant="outline"
          onClick={() => (step === 0 ? navigate('/kbs') : setStep(step - 1))}
          disabled={createMut.isPending}
        >
          {step === 0 ? '取消' : '上一步'}
        </Button>
        {step < STEPS.length - 1 ? (
          <Button onClick={() => setStep(step + 1)} disabled={step === 0 && !canNext0}>
            下一步
          </Button>
        ) : (
          <Button onClick={() => createMut.mutate()} disabled={createMut.isPending}>
            {createMut.isPending ? '创建中…' : '创建知识库'}
          </Button>
        )}
      </div>
    </div>
  );
};

const Field: React.FC<{
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}> = ({ label, hint, required, children }) => (
  <div className="space-y-1">
    <Label className="text-[12px] text-stone-600">
      {label}
      {required && <span className="ml-0.5 text-rose-500">*</span>}
      {hint && <span className="ml-1.5 text-[10.5px] font-normal text-stone-400">{hint}</span>}
    </Label>
    {children}
  </div>
);

const Row: React.FC<{ k: string; v: string; mono?: boolean }> = ({ k, v, mono }) => (
  <div className="flex gap-3">
    <span className="w-20 shrink-0 text-stone-400">{k}</span>
    <span className={cn('text-stone-800', mono && 'font-mono')}>{v || '—'}</span>
  </div>
);

const FileDrop: React.FC<{ files: File[]; onChange: (f: File[]) => void }> = ({
  files,
  onChange,
}) => {
  const add = (list: FileList | null) => {
    if (list) onChange([...files, ...Array.from(list)]);
  };
  return (
    <div>
      <label
        onDragOver={e => e.preventDefault()}
        onDrop={e => {
          e.preventDefault();
          add(e.dataTransfer.files);
        }}
        className="flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed border-stone-300 bg-stone-50/60 px-4 py-6 text-center transition hover:border-blue-300 hover:bg-blue-50/40"
      >
        <UploadCloud className="h-5 w-5 text-stone-400" strokeWidth={1.6} />
        <span className="text-[12px] text-stone-500">
          拖拽文件到此或<span className="text-blue-600">点击选择</span>（PDF / DOCX / TXT / MD…）
        </span>
        <input
          type="file"
          multiple
          className="hidden"
          onChange={e => {
            add(e.target.files);
            e.target.value = '';
          }}
        />
      </label>
      {files.length > 0 && (
        <ul className="mt-2 space-y-1">
          {files.map((f, i) => (
            <li
              key={`${f.name}-${i}`}
              className="flex items-center gap-2 rounded-md border border-stone-200 bg-white px-2.5 py-1.5 text-[11.5px]"
            >
              <FileText className="h-3.5 w-3.5 shrink-0 text-stone-400" />
              <span className="min-w-0 flex-1 truncate text-stone-700">{f.name}</span>
              <span className="tnum text-stone-400">{(f.size / 1024).toFixed(0)} KB</span>
              <button
                type="button"
                onClick={() => onChange(files.filter((_, j) => j !== i))}
                className="text-stone-400 hover:text-rose-500"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
