/** KB 详情页：tabs 概览 / 文档 / 检索测试 / 评估 / 配置
 *
 * Bundle 1（本提交）实现 概览 + 文档。其他 tab 留占位，由后续 C.2/C.3/C.4 填。
 */
import type { ReactElement } from 'react';
import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeft,
  BarChart3,
  FileText,
  FlaskConical,
  Search,
  Settings,
  ShieldCheck,
  Tag,
} from 'lucide-react';

import { SectionCard } from '@/core/components/table';
import { cn } from '@/core/lib/cn';
import { formatDateTime } from '@/core/lib/format';
import { CollectionsTab } from '@/system/kbs/components/collections-tab';
import { ConsistencyTab } from '@/system/kbs/components/consistency-tab';
import { DocumentTable } from '@/system/kbs/components/document-table';
import { DocumentUploadZone } from '@/system/kbs/components/document-upload-zone';
import { EvaluationListTab } from '@/system/kbs/components/evaluation-list';
import { HitTestPanel } from '@/system/kbs/components/hit-test-panel';
import { KbConfigForm } from '@/system/kbs/components/kb-config-form';
import { MetadataFieldsTab } from '@/system/kbs/components/metadata-fields-tab';
import { kbApi } from '@/system/kbs/services/kb';
import type { KbItem } from '@/system/kbs/types/kb';

type TabKey =
  | 'overview'
  | 'documents'
  | 'collections'
  | 'metadata'
  | 'search'
  | 'eval'
  | 'consistency'
  | 'config';

interface TabDef {
  key: TabKey;
  label: string;
  icon: ReactElement;
}

const RECALL_MODE_LABEL: Record<string, string> = {
  vector: '向量（语义）',
  hybrid: '混合',
  keyword: '关键词',
};

const CHUNK_MODE_LABEL: Record<string, string> = {
  fixed: '固定字数',
  paragraph: '按段落',
  sentence: '按句子',
  regex: '自定义正则',
  token: '按 Token',
  parent_child: '父子分层',
  qa: 'QA 问答',
};

// Dify 式左导航分两组：核心（文档/召回测试/概览）+ 进阶（集合/评测/一致性/设置）
const NAV_PRIMARY: TabDef[] = [
  { key: 'documents', label: '文档', icon: <FileText className="h-4 w-4" /> },
  { key: 'search', label: '召回测试', icon: <Search className="h-4 w-4" /> },
  { key: 'overview', label: '概览', icon: <BarChart3 className="h-4 w-4" /> },
];
const NAV_ADVANCED: TabDef[] = [
  { key: 'metadata', label: '元数据', icon: <Tag className="h-4 w-4" /> },
  { key: 'eval', label: '评测', icon: <FlaskConical className="h-4 w-4" /> },
  { key: 'consistency', label: '一致性', icon: <ShieldCheck className="h-4 w-4" /> },
  { key: 'config', label: '设置', icon: <Settings className="h-4 w-4" /> },
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

  const navBtn = (t: TabDef) => (
    <button
      key={t.key}
      type="button"
      onClick={() => setTab(t.key)}
      className={cn(
        'flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] font-medium transition',
        tab === t.key
          ? 'bg-blue-50 text-blue-700'
          : 'text-stone-600 hover:bg-stone-100 hover:text-stone-900',
      )}
    >
      {t.icon}
      {t.label}
    </button>
  );

  return (
    <div className="space-y-3">
      <Header kb={kbQ.data ?? null} loading={kbQ.isLoading} />
      <div className="flex gap-4">
        {/* 左导航（Dify 式） */}
        <nav className="w-40 shrink-0 space-y-0.5">
          {NAV_PRIMARY.map(navBtn)}
          <div className="my-2 border-t border-stone-200/60" />
          <div className="px-3 pb-1 text-[10.5px] tracking-wider text-stone-400 uppercase">
            进阶
          </div>
          {NAV_ADVANCED.map(navBtn)}
        </nav>

        {/* 主内容 */}
        <SectionCard className="min-w-0 flex-1">
          {tab === 'overview' && <OverviewTab kb={kbQ.data ?? null} />}
          {tab === 'documents' && <DocumentsTab kbId={kbId} />}
          {tab === 'collections' && <CollectionsTab kbId={kbId} />}
          {tab === 'metadata' && <MetadataFieldsTab kbId={kbId} />}
          {tab === 'search' &&
            (kbQ.data ? (
              <HitTestPanel kb={kbQ.data} />
            ) : (
              <PlaceholderTab title="召回测试" hint="加载 KB 信息中…" />
            ))}
          {tab === 'eval' && <EvaluationListTab kbId={kbId} />}
          {tab === 'consistency' && <ConsistencyTab kbId={kbId} />}
          {tab === 'config' &&
            (kbQ.data ? (
              <KbConfigForm kb={kbQ.data} />
            ) : (
              <PlaceholderTab title="设置" hint="加载中…" />
            ))}
        </SectionCard>
      </div>
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
        <span className="font-mono text-[11.5px] text-stone-500">{kb.kb_key}</span>
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
            { label: '默认召回数', value: kb.default_top_k },
            { label: '召回模式', value: RECALL_MODE_LABEL[kb.recall_mode] ?? kb.recall_mode },
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
            <div className="tnum mt-1 font-mono text-[20px] text-stone-900">{s.value}</div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3 text-[12.5px]">
        <KvCard label="知识库标识" value={kb.kb_key} mono />
        <KvCard
          label="向量模型"
          value={`${kb.embedding_model} · 维度 ${kb.embedding_dim}`}
          mono
        />
        <KvCard
          label="分块策略"
          value={
            kb.chunk_strategy
              ? `${CHUNK_MODE_LABEL[kb.chunk_strategy.mode] ?? kb.chunk_strategy.mode} · 块大小 ${kb.chunk_strategy.chunk_size ?? kb.chunk_size} · 重叠 ${kb.chunk_strategy.overlap ?? kb.chunk_overlap}`
              : `默认 · 块大小 ${kb.chunk_size} · 重叠 ${kb.chunk_overlap}`
          }
          mono
        />
        <KvCard label="描述" value={kb.description ?? '—'} />
        <KvCard label="创建时间" value={formatDateTime(kb.created_at)} mono />
        <KvCard label="更新时间" value={formatDateTime(kb.updated_at)} mono />
      </div>
    </div>
  );
};

const KvCard = ({ label, value, mono }: { label: string; value: string; mono?: boolean }) => (
  <div className="rounded-md border border-stone-200/70 bg-white px-3 py-2">
    <div className="text-[11px] text-stone-500">{label}</div>
    <div className={cn('mt-0.5 text-[12.5px] text-stone-800', mono && 'tnum font-mono')}>
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
