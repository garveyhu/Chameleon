/** KB 详情页：tabs 概览 / 文档 / 检索测试 / 评估 / 配置
 *
 * Bundle 1（本提交）实现 概览 + 文档。其他 tab 留占位，由后续 C.2/C.3/C.4 填。
 */

import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeft,
  BarChart3,
  FileText,
  FlaskConical,
  Search,
  Settings,
} from 'lucide-react';
import type { ReactElement } from 'react';
import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { SectionCard } from '@/core/components/table';
import { cn } from '@/core/lib/cn';
import { formatDateTime } from '@/core/lib/format';
import { DocumentTable } from '@/system/kbs/components/document-table';
import { DocumentUploadZone } from '@/system/kbs/components/document-upload-zone';
import { EvaluationListTab } from '@/system/kbs/components/evaluation-list';
import { KbConfigForm } from '@/system/kbs/components/kb-config-form';
import { RetrievalTest } from '@/system/kbs/components/retrieval-test';
import { kbApi } from '@/system/kbs/services/kb';
import type { KbItem } from '@/system/kbs/types/kb';

type TabKey = 'overview' | 'documents' | 'search' | 'eval' | 'config';

interface TabDef {
  key: TabKey;
  label: string;
  icon: ReactElement;
}

const TABS: TabDef[] = [
  { key: 'overview', label: '概览', icon: <BarChart3 className="h-3.5 w-3.5" /> },
  { key: 'documents', label: '文档', icon: <FileText className="h-3.5 w-3.5" /> },
  { key: 'search', label: '检索测试', icon: <Search className="h-3.5 w-3.5" /> },
  { key: 'eval', label: '评估', icon: <FlaskConical className="h-3.5 w-3.5" /> },
  { key: 'config', label: '配置', icon: <Settings className="h-3.5 w-3.5" /> },
];

export const KbDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const kbId = id ?? '';
  const [tab, setTab] = useState<TabKey>('documents');

  const kbQ = useQuery({
    queryKey: ['kb', kbId],
    queryFn: () => kbApi.get(kbId),
    enabled: !!kbId,
  });

  if (!kbId) {
    return (
      <SectionCard>
        <div className="p-6 text-sm text-stone-500">非法的 KB 编号</div>
      </SectionCard>
    );
  }

  return (
    <div className="space-y-3">
      <Header kb={kbQ.data ?? null} loading={kbQ.isLoading} />
      <SectionCard className="!p-0">
        <nav className="flex items-center gap-1 border-b border-stone-200/70 bg-warm-2/40 px-3 py-2">
          {TABS.map(t => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12.5px] font-medium transition',
                tab === t.key
                  ? 'bg-white text-stone-900 shadow-sm'
                  : 'text-stone-500 hover:bg-stone-100 hover:text-stone-800',
              )}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </nav>
        <div className="p-4">
          {tab === 'overview' && <OverviewTab kb={kbQ.data ?? null} />}
          {tab === 'documents' && <DocumentsTab kbId={kbId} />}
          {tab === 'search' &&
            (kbQ.data ? (
              <RetrievalTest kb={kbQ.data} />
            ) : (
              <PlaceholderTab title="检索测试" hint="加载 KB 信息中…" />
            ))}
          {tab === 'eval' && <EvaluationListTab kbId={kbId} />}
          {tab === 'config' &&
            (kbQ.data ? (
              <KbConfigForm kb={kbQ.data} />
            ) : (
              <PlaceholderTab title="KB 配置" hint="加载中…" />
            ))}
        </div>
      </SectionCard>
    </div>
  );
};

interface HeaderProps {
  kb: KbItem | null;
  loading: boolean;
}

const Header = ({ kb, loading }: HeaderProps) => (
  <div className="flex items-center gap-3">
    <Link
      to="/kbs"
      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12.5px] text-stone-500 hover:bg-stone-100 hover:text-stone-800"
    >
      <ArrowLeft className="h-3.5 w-3.5" /> 知识库
    </Link>
    <span className="text-stone-300">/</span>
    {loading ? (
      <span className="text-[12.5px] text-stone-400">加载中…</span>
    ) : kb ? (
      <div className="flex flex-1 items-baseline gap-2">
        <span className="text-[15px] font-medium text-stone-900">{kb.name}</span>
        <span className="font-mono text-[11.5px] text-stone-500">
          {kb.kb_key}
        </span>
        <span className="ml-auto" />
        <Link
          to={`/kbs/${kb.id}/chunking-preview`}
          className="inline-flex items-center gap-1 rounded-md border border-stone-200 bg-white px-2 py-1 text-[11.5px] text-stone-700 hover:border-amber-300 hover:bg-amber-50/40 hover:text-amber-700"
        >
          ✂︎ 切块预览
        </Link>
      </div>
    ) : (
      <span className="text-[12.5px] text-stone-400">未找到</span>
    )}
  </div>
);

const OverviewTab = ({ kb }: { kb: KbItem | null }) => {
  const stats = useMemo(
    () =>
      kb
        ? [
            { label: '文档总数', value: kb.document_count },
            { label: '切块总数', value: kb.chunk_count },
            { label: '默认 top_k', value: kb.default_top_k },
            { label: '召回模式', value: kb.recall_mode },
          ]
        : [],
    [kb],
  );

  if (!kb) return <div className="py-12 text-center text-sm text-stone-400">—</div>;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-3">
        {stats.map(s => (
          <div
            key={s.label}
            className="rounded-lg border border-stone-200/70 bg-stone-50/60 px-4 py-3"
          >
            <div className="text-[11px] text-stone-500">{s.label}</div>
            <div className="mt-1 font-mono text-[20px] tnum text-stone-900">
              {s.value}
            </div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3 text-[12.5px]">
        <KvCard label="kb_key" value={kb.kb_key} mono />
        <KvCard label="embedding_model" value={`${kb.embedding_model} · d=${kb.embedding_dim}`} mono />
        <KvCard
          label="chunk_strategy"
          value={
            kb.chunk_strategy
              ? `${kb.chunk_strategy.mode} · size=${kb.chunk_strategy.chunk_size ?? kb.chunk_size} · overlap=${kb.chunk_strategy.overlap ?? kb.chunk_overlap}`
              : `legacy · size=${kb.chunk_size} · overlap=${kb.chunk_overlap}`
          }
          mono
        />
        <KvCard label="description" value={kb.description ?? '—'} />
        <KvCard label="created_at" value={formatDateTime(kb.created_at)} mono />
        <KvCard label="updated_at" value={formatDateTime(kb.updated_at)} mono />
      </div>
    </div>
  );
};

const KvCard = ({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) => (
  <div className="rounded-md border border-stone-200/70 bg-white px-3 py-2">
    <div className="text-[11px] text-stone-500">{label}</div>
    <div
      className={cn(
        'mt-0.5 text-[12.5px] text-stone-800',
        mono && 'font-mono tnum',
      )}
    >
      {value}
    </div>
  </div>
);

const DocumentsTab = ({ kbId }: { kbId: import('@/core/types/api').EntityId }) => (
  <div className="space-y-4">
    <DocumentUploadZone kbId={kbId} />
    <DocumentTable kbId={kbId} />
  </div>
);

const PlaceholderTab = ({ title, hint }: { title: string; hint: string }) => (
  <div className="flex h-[260px] flex-col items-center justify-center gap-2 text-stone-400">
    <div className="text-[14px] font-medium text-stone-500">{title}</div>
    <div className="text-[12px]">{hint}</div>
  </div>
);
