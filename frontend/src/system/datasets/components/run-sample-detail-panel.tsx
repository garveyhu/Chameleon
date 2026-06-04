/** 样本详情侧栏 —— 整页右侧滑出（非行内嵌套小框）。
 *  输入 / 预期 / 实际 / score / reason / field_scores + 「查看调用 trace」下钻。 */

import { ExternalLink, X } from 'lucide-react';
import { Link } from 'react-router-dom';

import { JsonEditor } from '@/core/components/ui/json-editor';
import { cn } from '@/core/lib/cn';
import { formatScore, scoreBg } from '@/core/lib/score';
import { FieldScores } from '@/system/datasets/components/run-sample-field-scores';
import type { DatasetRunItemRow } from '@/system/datasets/types/dataset';

const noop = () => {};

const toText = (v: unknown): string =>
  v == null ? '' : typeof v === 'string' ? v : JSON.stringify(v, null, 2);

interface Props {
  ri: DatasetRunItemRow;
  onClose: () => void;
}

export const RunSampleDetailPanel = ({ ri, onClose }: Props) => (
  <aside className="flex h-full w-[420px] shrink-0 flex-col overflow-hidden border-l border-stone-200 bg-[var(--color-paper)]">
    <header className="flex items-center justify-between border-b border-stone-200 px-4 py-3">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[10.5px] text-stone-400">
          样本 …{String(ri.dataset_item_id).slice(-6)}
        </span>
        <span className={cn('rounded px-1.5 py-0.5 text-[10.5px]', scoreBg(ri.score))}>
          {ri.score != null ? formatScore(ri.score) : '无分'}
        </span>
        {ri.duration_ms != null && (
          <span className="text-[10.5px] text-stone-400">{ri.duration_ms}ms</span>
        )}
      </div>
      <button
        type="button"
        onClick={onClose}
        title="收起"
        className="rounded p-1 text-stone-400 hover:bg-stone-100 hover:text-stone-700"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </header>

    <div className="flex-1 space-y-3 overflow-auto px-4 py-3">
      {ri.request_id ? (
        <Link
          to={`/traces/${encodeURIComponent(ri.request_id)}`}
          className="inline-flex items-center gap-1 rounded-md bg-sky-50 px-2 py-1 text-[11px] text-sky-700 transition hover:bg-sky-100"
        >
          <ExternalLink className="h-3.5 w-3.5" /> 查看调用 trace
        </Link>
      ) : (
        <span className="inline-flex items-center gap-1 rounded-md bg-stone-50 px-2 py-1 text-[11px] text-stone-400">
          该样本无 trace（迁移前运行）
        </span>
      )}

      <div>
        <div className="mb-1 text-[10.5px] text-stone-500">输入</div>
        <JsonEditor
          value={toText(ri.input_payload)}
          onChange={noop}
          readOnly
          wrap
          label="输入"
          minHeight="56px"
          maxHeight="160px"
        />
      </div>

      <div>
        <div className="mb-1 text-[10.5px] text-emerald-600">理想回答</div>
        <JsonEditor
          value={toText(ri.expected_output)}
          onChange={noop}
          readOnly
          wrap
          label="预期"
          minHeight="56px"
          maxHeight="200px"
        />
      </div>
      <div>
        <div className="mb-1 text-[10.5px] text-sky-600">模型回答</div>
        <JsonEditor
          value={toText(ri.actual_output)}
          onChange={noop}
          readOnly
          wrap
          label="实际"
          minHeight="56px"
          maxHeight="200px"
        />
      </div>
      {ri.reference_output && (
        <div>
          <div className="mb-1 text-[10.5px] text-violet-600">参照回答（GSB 对照）</div>
          <JsonEditor
            value={toText(ri.reference_output)}
            onChange={noop}
            readOnly
            wrap
            label="参照"
            minHeight="56px"
            maxHeight="200px"
          />
        </div>
      )}

      <FieldScores fieldScores={ri.field_scores} score={ri.score} />

      <div>
        <div className="mb-1 text-[10.5px] text-stone-500">评分理由</div>
        {ri.score_reason ? (
          <p className="rounded border border-stone-200 bg-white px-2 py-1.5 text-[11.5px] leading-relaxed text-stone-700">
            {ri.score_reason}
          </p>
        ) : (
          <p className="rounded border border-dashed border-stone-200 px-2 py-1.5 text-[11px] text-stone-400">
            当前评分器未输出理由（升级评分体系后，AI / DSL 评分将给出逐项理由）
          </p>
        )}
      </div>

      {ri.error && (
        <div>
          <div className="mb-1 text-[10.5px] text-rose-500">错误</div>
          <pre className="overflow-auto rounded border border-rose-100 bg-rose-50 px-2 py-1.5 text-[10.5px] text-rose-700">
            {JSON.stringify(ri.error, null, 2)}
          </pre>
        </div>
      )}
    </div>
  </aside>
);
