/** JsonViewer —— 缩进 / 折叠 / 高亮 / 复制 / 搜索（自实现，零依赖） */

import { Check, ChevronDown, ChevronRight, Copy, Search } from 'lucide-react';
import { useMemo, useState } from 'react';

import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';

interface Props {
  value: unknown;
  /** 顶层默认是否展开（默认 true） */
  defaultExpanded?: boolean;
  /** 是否显示搜索框（默认 true） */
  searchable?: boolean;
  className?: string;
  /** 整体高度限制（默认 70vh，超出滚动） */
  maxHeight?: string;
}

export const JsonViewer = ({
  value,
  defaultExpanded = true,
  searchable = true,
  className,
  maxHeight = '70vh',
}: Props) => {
  const [query, setQuery] = useState('');
  const [copied, setCopied] = useState(false);

  const fullText = useMemo(() => {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }, [value]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(fullText);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error('复制失败');
    }
  };

  return (
    <div className={cn('flex flex-col overflow-hidden rounded-md border border-stone-200 bg-white', className)}>
      {searchable && (
        <div className="flex items-center gap-2 border-b border-stone-200 bg-stone-50/60 px-2 py-1.5">
          <Search className="h-3.5 w-3.5 text-stone-400" />
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="搜索 key 或 value…"
            className="flex-1 bg-transparent text-[12.5px] outline-none placeholder:text-stone-400"
          />
          <button
            type="button"
            onClick={copy}
            className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-[11.5px] text-stone-600 hover:bg-stone-200 hover:text-stone-900"
            title="复制 JSON"
          >
            {copied ? (
              <Check className="h-3 w-3 text-emerald-600" />
            ) : (
              <Copy className="h-3 w-3" />
            )}
            {copied ? '已复制' : '复制'}
          </button>
        </div>
      )}
      <div
        className="overflow-auto p-2 font-mono text-[12px] leading-snug"
        style={{ maxHeight }}
      >
        <Node
          value={value}
          path=""
          depth={0}
          query={query.trim().toLowerCase()}
          defaultExpanded={defaultExpanded}
        />
      </div>
    </div>
  );
};

interface NodeProps {
  name?: string;
  value: unknown;
  path: string;
  depth: number;
  query: string;
  defaultExpanded: boolean;
  /** true → 内层节点也跟着展开（搜索命中场景） */
  forceExpand?: boolean;
}

function nodeMatchesQuery(name: string | undefined, value: unknown, q: string): boolean {
  if (!q) return false;
  if (name && name.toLowerCase().includes(q)) return true;
  if (typeof value === 'string' && value.toLowerCase().includes(q)) return true;
  if (typeof value === 'number' && String(value).includes(q)) return true;
  if (typeof value === 'boolean' && String(value).includes(q)) return true;
  if (value && typeof value === 'object') {
    if (Array.isArray(value)) {
      for (const v of value) if (nodeMatchesQuery(undefined, v, q)) return true;
    } else {
      for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
        if (nodeMatchesQuery(k, v, q)) return true;
      }
    }
  }
  return false;
}

const Node = ({
  name,
  value,
  path,
  depth,
  query,
  defaultExpanded,
  forceExpand,
}: NodeProps) => {
  const hasMatch = query ? nodeMatchesQuery(name, value, query) : true;
  const initialExpanded = forceExpand || (defaultExpanded && depth < 3) || (!!query && hasMatch);
  const [expanded, setExpanded] = useState(initialExpanded);

  // 隐藏不匹配的子树（提升搜索体验）
  if (query && !hasMatch) return null;

  const indent = { paddingLeft: depth * 12 };

  // primitive
  if (value === null) return <Row indent={indent} name={name} primitive={<span className="text-stone-400">null</span>} query={query} />;
  if (value === undefined) return <Row indent={indent} name={name} primitive={<span className="text-stone-400">undefined</span>} query={query} />;
  if (typeof value === 'string') {
    return (
      <Row
        indent={indent}
        name={name}
        primitive={<span className="text-emerald-700">{highlight(JSON.stringify(value), query)}</span>}
        query={query}
      />
    );
  }
  if (typeof value === 'number') {
    return <Row indent={indent} name={name} primitive={<span className="text-sky-700">{value}</span>} query={query} />;
  }
  if (typeof value === 'boolean') {
    return (
      <Row indent={indent} name={name} primitive={<span className="text-purple-700">{String(value)}</span>} query={query} />
    );
  }

  // object / array
  const isArr = Array.isArray(value);
  const entries = isArr
    ? (value as unknown[]).map((v, i) => [String(i), v] as const)
    : Object.entries(value as Record<string, unknown>);
  const empty = entries.length === 0;
  const openBr = isArr ? '[' : '{';
  const closeBr = isArr ? ']' : '}';

  return (
    <div>
      <div className="flex items-start" style={indent}>
        {!empty && (
          <button
            type="button"
            onClick={() => setExpanded(e => !e)}
            className="mr-1 text-stone-400 hover:text-stone-600"
            aria-label={expanded ? 'collapse' : 'expand'}
          >
            {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          </button>
        )}
        {empty && <span className="mr-1 inline-block w-3" />}
        {name !== undefined && (
          <span className="text-stone-700">{highlight(JSON.stringify(name), query)}: </span>
        )}
        <span className="text-stone-500">{openBr}</span>
        {!expanded && !empty && (
          <span className="ml-1 text-stone-400">
            {isArr ? `${entries.length} item${entries.length > 1 ? 's' : ''}` : `${entries.length} keys`}
          </span>
        )}
        {(empty || !expanded) && <span className="text-stone-500">{closeBr}</span>}
        <CopyButton path={path} value={value} />
      </div>
      {expanded && !empty && (
        <div>
          {entries.map(([k, v]) => (
            <Node
              key={k}
              name={isArr ? undefined : k}
              value={v}
              path={path ? `${path}.${k}` : k}
              depth={depth + 1}
              query={query}
              defaultExpanded={defaultExpanded}
              forceExpand={!!query}
            />
          ))}
          <div style={{ paddingLeft: depth * 12 + 16 }} className="text-stone-500">
            {closeBr}
          </div>
        </div>
      )}
    </div>
  );
};

interface RowProps {
  indent: { paddingLeft: number };
  name?: string;
  primitive: React.ReactNode;
  query: string;
}

const Row = ({ indent, name, primitive, query }: RowProps) => (
  <div className="group flex items-start" style={indent}>
    <span className="mr-1 inline-block w-3 shrink-0" />
    {name !== undefined && (
      <span className="shrink-0 text-stone-700">
        {highlight(JSON.stringify(name), query)}:&nbsp;
      </span>
    )}
    {/* 值列 min-w-0 flex-1：长字符串在此列内换行，续行挂在值起点下方对齐 */}
    <span className="min-w-0 flex-1 break-words">{primitive}</span>
  </div>
);

const CopyButton = ({ path, value }: { path: string; value: unknown }) => {
  const [copied, setCopied] = useState(false);
  const onClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    const text =
      typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value);
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error('复制失败');
    }
  };
  return (
    <button
      type="button"
      onClick={onClick}
      className="ml-2 hidden rounded p-0.5 text-stone-400 hover:bg-stone-100 hover:text-stone-700 group-hover:inline-flex"
      title={`复制 ${path || '$'}`}
    >
      {copied ? <Check className="h-3 w-3 text-emerald-600" /> : <Copy className="h-3 w-3" />}
    </button>
  );
};

function highlight(text: string, query: string): React.ReactNode {
  if (!query) return text;
  const lower = text.toLowerCase();
  const idx = lower.indexOf(query);
  if (idx < 0) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="rounded bg-amber-100 px-0.5 text-stone-900">
        {text.slice(idx, idx + query.length)}
      </mark>
      {text.slice(idx + query.length)}
    </>
  );
}
