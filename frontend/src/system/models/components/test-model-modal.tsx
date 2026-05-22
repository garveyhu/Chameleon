/** 模型连通性测试弹窗：SSE 流式输出 */

import { AlertCircle, CheckCircle2, Loader2, X, Zap } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import {
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { Label } from '@/core/components/ui/label';
import { cn } from '@/core/lib/cn';
import { modelApi, type TestStreamChunk } from '@/system/models/services/model';
import type { ModelItem } from '@/system/models/types/model';

interface TestModelModalProps {
  model: ModelItem | null;
  onClose: () => void;
}

type RunState = 'idle' | 'running' | 'done' | 'error' | 'aborted';

const DEFAULT_PROMPT = '请用一句话简短自我介绍。';

export const TestModelModal: React.FC<TestModelModalProps> = ({ model, onClose }) => {
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [output, setOutput] = useState('');
  const [state, setState] = useState<RunState>('idle');
  const [meta, setMeta] = useState<TestStreamChunk['meta'] | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [usage, setUsage] = useState<TestStreamChunk['usage']>(null);
  const [errorText, setErrorText] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const outputRef = useRef<HTMLPreElement | null>(null);

  // 输出自动滚到底
  useEffect(() => {
    if (outputRef.current) outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, [output]);

  // 关闭弹窗时清理流
  useEffect(() => {
    if (!model) {
      abortRef.current?.abort();
      abortRef.current = null;
      setOutput('');
      setState('idle');
      setMeta(null);
      setLatencyMs(null);
      setUsage(null);
      setErrorText(null);
      setPrompt(DEFAULT_PROMPT);
    }
  }, [model]);

  const start = async () => {
    if (!model) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setOutput('');
    setMeta(null);
    setLatencyMs(null);
    setUsage(null);
    setErrorText(null);
    setState('running');
    try {
      await modelApi.streamTest(model.id, {
        prompt: model.kind === 'chat' ? prompt.trim() || undefined : undefined,
        signal: ctrl.signal,
        onChunk: chunk => {
          if (chunk.meta) setMeta(chunk.meta);
          if (chunk.delta) setOutput(prev => prev + chunk.delta);
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

  const isChat = model?.kind === 'chat';
  const running = state === 'running';

  return (
    <Modal open={!!model} onOpenChange={o => !o && onClose()}>
      <ModalContent size="lg">
        <ModalHeader>
          <ModalTitle className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-amber-500" />
            <span>模型连通性测试</span>
            {model ? (
              <span className="font-mono text-[12.5px] font-normal text-stone-500">
                {model.provider_code} · {model.code}
              </span>
            ) : null}
          </ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-3">
          {isChat ? (
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
          ) : (
            <p className="text-[12px] text-stone-500">
              embedding 模型测试将对 <span className="font-mono">{`"hello"`}</span> 取向量并校验维度。
            </p>
          )}

          <div className="rounded-md border border-stone-200 bg-stone-50">
            <div className="flex items-center justify-between border-b border-stone-200 px-3 py-1.5">
              <div className="flex items-center gap-2 text-[11px] text-stone-500">
                <StateBadge state={state} />
                {meta ? (
                  <span className="font-mono">{meta.kind} / {meta.model}</span>
                ) : null}
                {latencyMs !== null ? (
                  <span className="font-mono">· {latencyMs}ms</span>
                ) : null}
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
            <Button variant="primary" onClick={start} disabled={!model}>
              {state === 'done' || state === 'error' || state === 'aborted' ? (
                <>
                  <Zap className="h-3.5 w-3.5" /> 重新测试
                </>
              ) : (
                <>
                  <Zap className="h-3.5 w-3.5" /> 开始测试
                </>
              )}
            </Button>
          )}
        </ModalFooter>
      </ModalContent>
    </Modal>
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
