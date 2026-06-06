/** 模型连通性测试弹窗：SSE 流式输出 */

import { AlertCircle, CheckCircle2, Image as ImageIcon, Loader2, X, Zap } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import {
  GenerationPanel,
  type GenerationPanelHandle,
} from '@/core/components/common/generation-panel';
import { ImageGenLoading } from '@/core/components/common/image-gen-loading';
import { Badge } from '@/core/components/ui/badge';
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
import { cn } from '@/core/lib/cn';
import { modelApi, type TestStreamChunk } from '@/system/models/services/model';
import type { ModelItem } from '@/system/models/types/model';

interface TestModelModalProps {
  model: ModelItem | null;
  onClose: () => void;
}

type RunState = 'idle' | 'running' | 'done' | 'error' | 'aborted';

const DEFAULT_PROMPT = '请用一句话简短自我介绍。';

// 外壳保持挂载做开合动画；内容按 model.id remount —— 状态随开/关自然重置，
// 不用 useEffect 同步 props（react-hooks/set-state-in-effect）。
export const TestModelModal: React.FC<TestModelModalProps> = ({ model, onClose }) => (
  <Modal open={!!model} onOpenChange={o => !o && onClose()}>
    <ModalContent size="lg">
      {model ? <TestModelContent key={String(model.id)} model={model} onClose={onClose} /> : null}
    </ModalContent>
  </Modal>
);

const TestModelContent = ({ model, onClose }: { model: ModelItem; onClose: () => void }) => {
  const [prompt, setPrompt] = useState(model.kind === 'image' ? '' : DEFAULT_PROMPT);
  const [output, setOutput] = useState('');
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [state, setState] = useState<RunState>('idle');
  const [meta, setMeta] = useState<TestStreamChunk['meta'] | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [usage, setUsage] = useState<TestStreamChunk['usage']>(null);
  const [errorText, setErrorText] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const outputRef = useRef<HTMLPreElement | null>(null);
  const genRef = useRef<GenerationPanelHandle | null>(null);

  // 输出自动滚到底
  useEffect(() => {
    if (outputRef.current) outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, [output]);

  // 卸载（关闭弹窗）时中断流 —— 仅 cleanup，无 setState
  useEffect(() => () => abortRef.current?.abort(), []);

  const start = async () => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setOutput('');
    setImageUrl(null);
    setVideoUrl(null);
    setMeta(null);
    setLatencyMs(null);
    setUsage(null);
    setErrorText(null);
    setState('running');
    const isGen = model.kind === 'image' || model.kind === 'video';
    const gen = isGen ? genRef.current?.getRequest() : undefined;
    try {
      await modelApi.streamTest(model.id, {
        prompt: isGen
          ? gen?.prompt || undefined
          : model.kind === 'chat'
            ? prompt.trim() || undefined
            : undefined,
        params: isGen ? gen?.params : undefined,
        inputImages: isGen ? gen?.input_images : undefined,
        signal: ctrl.signal,
        onChunk: chunk => {
          if (chunk.meta) setMeta(chunk.meta);
          if (chunk.delta) setOutput(prev => prev + chunk.delta);
          if (chunk.image_chunk?.url) setImageUrl(chunk.image_chunk.url);
          if (chunk.video_chunk?.url) setVideoUrl(chunk.video_chunk.url);
          if (chunk.error) {
            setErrorText(`${chunk.error.type}: ${chunk.error.message}`);
            setState('error');
          }
          if (chunk.end) {
            if (typeof chunk.latency_ms === 'number') setLatencyMs(chunk.latency_ms);
            setUsage(chunk.usage ?? null);
            setState(prev => (prev === 'error' ? 'error' : 'done'));
          }
        },
      });
      setState(prev => (prev === 'running' ? 'done' : prev));
    } catch (e) {
      if (ctrl.signal.aborted) {
        setState('aborted');
      } else {
        setErrorText(e instanceof Error ? e.message : String(e));
        setState('error');
      }
    } finally {
      abortRef.current = null;
    }
  };

  const stop = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setState('aborted');
  };

  const isChat = model.kind === 'chat';
  const isImage = model.kind === 'image';
  const isVideo = model.kind === 'video';
  const isGen = isImage || isVideo;
  const running = state === 'running';

  return (
    <>
      <ModalHeader>
        <ModalTitle className="flex items-center gap-2">
          <Zap className="h-4 w-4 text-amber-500" />
          <span>模型连通性测试</span>
          <span className="font-mono text-[12.5px] font-normal text-stone-500">
            {model.provider_code} · {model.code}
          </span>
        </ModalTitle>
      </ModalHeader>
      <ModalBody className="space-y-3">
        {isGen ? (
          <GenerationPanel
            ref={genRef}
            modelId={model.id}
            disabled={running}
            promptPlaceholder={
              isVideo
                ? '描述镜头运动 / 画面变化…'
                : '一只橘猫坐在窗台上，柔和晨光（留空用默认提示词）'
            }
          />
        ) : isChat ? (
          <div className="space-y-1.5">
            <Label className="text-[12px] text-stone-600">测试 prompt</Label>
            <Input
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              placeholder={DEFAULT_PROMPT}
              disabled={running}
              className="font-mono text-[12px]"
            />
          </div>
        ) : model.kind === 'rerank' ? (
          <p className="text-[12px] text-stone-500">
            rerank 模型测试将对一条 query + 两条候选文档打分，校验能正确排序。
          </p>
        ) : (
          <p className="text-[12px] text-stone-500">
            embedding 模型测试将对 <span className="font-mono">{`"hello"`}</span> 取向量并校验维度。
          </p>
        )}

        {isGen ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-[11px] text-stone-500">
              <StateBadge state={state} />
              {meta ? <span className="font-mono">{meta.kind} / {meta.model}</span> : null}
              {latencyMs !== null ? (
                <span className="font-mono">· {(latencyMs / 1000).toFixed(1)}s</span>
              ) : null}
            </div>
            {state === 'running' ? (
              <ImageGenLoading
                hint={
                  isVideo
                    ? '图生视频通常需数分钟，请耐心等待'
                    : '远程模型通常数秒；本地 ComfyUI 首次含模型加载可能数分钟'
                }
              />
            ) : videoUrl ? (
              <div className="overflow-hidden rounded-xl border border-stone-200 bg-black">
                <video src={videoUrl} controls className="mx-auto max-h-[420px] w-auto" />
              </div>
            ) : imageUrl ? (
              <div className="overflow-hidden rounded-xl border border-stone-200 bg-white">
                <img
                  src={imageUrl}
                  alt="生成结果"
                  className="mx-auto max-h-[420px] w-auto object-contain"
                />
              </div>
            ) : errorText ? (
              <div className="flex items-start gap-1.5 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2.5 text-[11.5px] text-rose-700">
                <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{errorText}</span>
              </div>
            ) : (
              <div className="flex aspect-[4/3] w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-stone-200 bg-stone-50/60 text-stone-400">
                <ImageIcon className="h-8 w-8 text-stone-300" />
                <span className="text-[12px]">
                  点击「开始测试」生成{isVideo ? '视频' : '图片'}
                </span>
              </div>
            )}
          </div>
        ) : (
          <div className="rounded-md border border-stone-200 bg-stone-50">
            <div className="flex items-center justify-between border-b border-stone-200 px-3 py-1.5">
              <div className="flex items-center gap-2 text-[11px] text-stone-500">
                <StateBadge state={state} />
                {meta ? <span className="font-mono">{meta.kind} / {meta.model}</span> : null}
                {latencyMs !== null ? <span className="font-mono">· {latencyMs}ms</span> : null}
              </div>
              {usage ? (
                <span className="font-mono text-[11px] text-stone-500">
                  tokens in/out: {usage.input_tokens}/{usage.output_tokens}
                </span>
              ) : null}
            </div>
            <pre
              ref={outputRef}
              className={cn(
                'max-h-[280px] min-h-[120px] overflow-auto whitespace-pre-wrap px-3 py-2 font-mono text-[12px] leading-relaxed text-stone-800',
                state === 'idle' && 'text-stone-400',
              )}
            >
              {output || (state === 'idle' ? '点击「开始测试」运行...' : '')}
              {running ? (
                <span className="inline-block h-3 w-1.5 animate-pulse bg-stone-400 align-middle" />
              ) : null}
            </pre>
            {errorText ? (
              <div className="flex items-start gap-1.5 border-t border-rose-200 bg-rose-50 px-3 py-2 text-[11.5px] text-rose-700">
                <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span className="font-mono">{errorText}</span>
              </div>
            ) : null}
          </div>
        )}
      </ModalBody>
      <ModalFooter>
        <Button variant="ghost" onClick={onClose} disabled={running}>
          关闭
        </Button>
        {running ? (
          <Button variant="outline" onClick={stop}>
            <X className="h-3.5 w-3.5" /> 中断
          </Button>
        ) : (
          <Button variant="primary" onClick={start}>
            <Zap className="h-3.5 w-3.5" />
            {state === 'done' || state === 'error' || state === 'aborted' ? '重新测试' : '开始测试'}
          </Button>
        )}
      </ModalFooter>
    </>
  );
};

const StateBadge = ({ state }: { state: RunState }) => {
  if (state === 'running') {
    return (
      <Badge variant="primary" className="gap-1">
        <Loader2 className="h-3 w-3 animate-spin" /> 流式中
      </Badge>
    );
  }
  if (state === 'done') {
    return (
      <Badge variant="success" className="gap-1">
        <CheckCircle2 className="h-3 w-3" /> 完成
      </Badge>
    );
  }
  if (state === 'error') {
    return (
      <Badge variant="danger" className="gap-1">
        <AlertCircle className="h-3 w-3" /> 失败
      </Badge>
    );
  }
  if (state === 'aborted') {
    return <Badge variant="default">已中断</Badge>;
  }
  return <Badge variant="default">未运行</Badge>;
};
