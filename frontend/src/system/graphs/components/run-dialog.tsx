/** RunDialog —— 运行工作流：给 input、跑、看结果（调试闭环核心 UI）
 *
 * Test Run：流式调试，不落库；节点状态实时回投 canvas + 这里逐节点列出。
 * Run：持久化执行，写 call_logs（trace tree 可见）。
 * 两种模式共用同一份 input；input 按 graphId 记忆到 localStorage。
 */

import { Play, Zap } from 'lucide-react';
import { useMemo, useState } from 'react';

import { JsonViewer } from '@/core/components/common/json-viewer';
import { Button } from '@/core/components/ui/button';
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import { Textarea } from '@/core/components/ui/textarea';
import { formatDurationMs } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import {
  NodeRunResult,
  NodeRunStatusBadge,
} from '@/system/graphs/components/node-run-result';
import type { GraphRunner } from '@/system/graphs/hooks/use-graph-runner';
import type { GraphNodeType, NodeRunView } from '@/system/graphs/types/graph';

const inputKey = (graphId: string) => `wf:run-input:${graphId}`;

interface NodeMeta {
  id: string;
  label: string;
  type: GraphNodeType;
}

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  graphId: string;
  graphName: string;
  isDirty: boolean;
  runner: GraphRunner;
  nodeMeta: NodeMeta[];
}

export const RunDialog = ({
  open,
  onOpenChange,
  graphId,
  graphName,
  isDirty,
  runner,
  nodeMeta,
}: Props) => {
  // 仅在 open 时挂载（见 editor 的条件渲染），故初始值即「上次输入」
  const [text, setText] = useState(
    () => localStorage.getItem(inputKey(graphId)) || '{}',
  );
  const [expandedNode, setExpandedNode] = useState<string | null>(null);

  const parsed = useMemo((): {
    value: Record<string, unknown> | null;
    error: string | null;
  } => {
    const t = text.trim();
    if (!t) return { value: {}, error: null };
    try {
      const v = JSON.parse(t);
      if (typeof v !== 'object' || v === null || Array.isArray(v)) {
        return { value: null, error: 'input 必须是一个 JSON 对象' };
      }
      return { value: v as Record<string, unknown>, error: null };
    } catch (e) {
      return { value: null, error: (e as Error).message };
    }
  }, [text]);

  const running = runner.phase === 'running';

  const trigger = async (mode: 'test' | 'persist') => {
    if (!parsed.value) return;
    localStorage.setItem(inputKey(graphId), text);
    try {
      if (mode === 'test') {
        await runner.runTest(parsed.value);
      } else {
        await runner.runPersist(parsed.value);
        toast.success('已持久化执行（trace 写入 call_logs）');
      }
    } catch (e) {
      toast.error(`执行失败：${(e as Error).message}`);
    }
  };

  return (
    <Modal open={open} onOpenChange={onOpenChange}>
      <ModalContent size="lg" className="max-h-[88vh]">
        <ModalHeader>
          <ModalTitle>运行 · {graphName}</ModalTitle>
        </ModalHeader>
        <ModalBody className="flex max-h-[calc(88vh-3.5rem)] flex-col gap-3 overflow-y-auto">
          {/* 输入 */}
          <div>
            <label className="mb-1 block text-[11.5px] text-stone-600">
              输入（JSON 对象，作为工作流的 input；start 节点透传给首个节点）
            </label>
            <Textarea
              value={text}
              onChange={e => setText(e.target.value)}
              rows={4}
              spellCheck={false}
              placeholder='{ "query": "你好" }'
              className="font-mono text-[12px]"
            />
            {parsed.error && (
              <div className="mt-1 text-[10.5px] text-rose-600">
                JSON 解析错误：{parsed.error}
              </div>
            )}
            {isDirty && (
              <div className="mt-1 text-[10.5px] text-amber-600">
                画布有未保存改动 —— 运行前会先自动保存草稿，确保跑的是当前画布。
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            <Button
              size="sm"
              onClick={() => trigger('test')}
              disabled={!parsed.value || running}
            >
              <Play className="mr-1 h-3 w-3" />
              Test Run
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => trigger('persist')}
              disabled={!parsed.value || running}
            >
              <Zap className="mr-1 h-3 w-3" />
              Run（持久化）
            </Button>
            <span className="text-[10.5px] text-stone-400">
              Test Run 不落库、实时流式；Run 写 call_logs
            </span>
          </div>

          {/* 运行摘要 */}
          {runner.phase !== 'idle' && (
            <div className="flex items-center gap-2 border-t border-stone-200/70 pt-3">
              <NodeRunStatusBadge
                status={
                  runner.phase === 'running'
                    ? 'running'
                    : runner.phase === 'success'
                      ? 'success'
                      : 'failed'
                }
              />
              {runner.durationMs != null && (
                <span className="tnum text-[11px] text-stone-500">
                  {formatDurationMs(runner.durationMs)}
                </span>
              )}
              {runner.nodeCount != null && (
                <span className="text-[11px] text-stone-500">
                  {runner.nodeCount} 节点
                </span>
              )}
              <span className="ml-auto text-[10.5px] text-stone-400">
                {runner.persisted ? '持久化执行' : '调试运行'}
              </span>
            </div>
          )}

          {/* 节点进度（仅 Test Run 有逐节点；持久化只给最终结果） */}
          {!runner.persisted && runner.phase !== 'idle' && (
            <div className="flex flex-col gap-1">
              {nodeMeta.map(n => {
                const run: NodeRunView | undefined = runner.nodeRuns[n.id];
                const status = run?.status ?? 'pending';
                const opened = expandedNode === n.id;
                return (
                  <div
                    key={n.id}
                    className="rounded-md border border-stone-200 bg-white"
                  >
                    <button
                      type="button"
                      onClick={() => setExpandedNode(opened ? null : n.id)}
                      disabled={!run}
                      className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-[11.5px] disabled:opacity-60"
                    >
                      <span className="truncate text-stone-800">{n.label}</span>
                      <span className="font-mono text-[10px] text-stone-400">
                        {n.type}
                      </span>
                      <span className="ml-auto">
                        <NodeRunStatusBadge status={status} />
                      </span>
                    </button>
                    {opened && run && (
                      <div className="border-t border-stone-100 px-2 py-2">
                        <NodeRunResult run={run} />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* 最终输出 / 错误 */}
          {runner.phase === 'failed' && runner.runError && (
            <div className="rounded-md border border-rose-200 bg-rose-50 px-2.5 py-2 text-[11.5px] text-rose-700">
              <div className="font-mono text-[10px] uppercase tracking-wide text-rose-400">
                {runner.runError.type}
              </div>
              <div className="break-words">{runner.runError.message}</div>
            </div>
          )}
          {runner.phase === 'success' &&
            runner.finalOutput !== undefined &&
            runner.finalOutput !== null && (
              <div>
                <div className="mb-1 text-[10.5px] uppercase tracking-wide text-stone-400">
                  最终输出
                </div>
                <JsonViewer value={runner.finalOutput} maxHeight="280px" />
              </div>
            )}
        </ModalBody>
      </ModalContent>
    </Modal>
  );
};
