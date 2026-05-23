/** Template Gallery —— P22.5 PR #83
 *
 * 公共模板列表（默认 only verified=True）；卡片网格 + 类别过滤 + 一键安装。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  BookOpen,
  Bot,
  CircleCheck,
  Download,
  Eye,
  EyeOff,
  Layers,
  Sparkles,
  Workflow,
} from 'lucide-react';
import { useState } from 'react';

import { SectionCard } from '@/core/components/table';
import { Button } from '@/core/components/ui/button';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import { appTemplateApi } from '@/system/marketplace/services/template';
import type {
  AppTemplateCategory,
  AppTemplateItem,
} from '@/system/marketplace/types/template';

const CATEGORIES: {
  key: AppTemplateCategory | 'all';
  label: string;
  icon: typeof Bot;
}[] = [
  { key: 'all', label: '全部', icon: Sparkles },
  { key: 'assistant', label: 'Assistant', icon: Bot },
  { key: 'agent', label: 'Agent', icon: Bot },
  { key: 'workflow', label: 'Workflow', icon: Workflow },
  { key: 'rag', label: 'RAG', icon: BookOpen },
];

const CAT_COLORS: Record<string, string> = {
  assistant: 'bg-blue-50 text-blue-700',
  agent: 'bg-fuchsia-50 text-fuchsia-700',
  workflow: 'bg-emerald-50 text-emerald-700',
  rag: 'bg-amber-50 text-amber-700',
};

export const TemplateGalleryPage = () => {
  const qc = useQueryClient();
  const [category, setCategory] = useState<AppTemplateCategory | 'all'>(
    'all',
  );
  const [showUnverified, setShowUnverified] = useState(false);

  const listQ = useQuery({
    queryKey: ['app-templates', category, showUnverified],
    queryFn: () =>
      appTemplateApi.list({
        category: category === 'all' ? undefined : category,
        only_verified: !showUnverified,
        limit: 50,
      }),
  });

  const installMut = useMutation({
    mutationFn: (id: AppTemplateItem['id']) => appTemplateApi.install(id),
    onSuccess: r => {
      toast.success(`已安装 "${r.template_name}"`);
      qc.invalidateQueries({ queryKey: ['app-templates'] });
    },
    onError: e => toast.error('安装失败：' + (e as Error).message),
  });

  return (
    <div className="space-y-3">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-stone-500" />
          <h1 className="text-[15px] font-medium text-stone-800">
            应用模板
          </h1>
          <span className="text-[11px] text-stone-400">
            {listQ.data?.length ?? '...'} 个
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-md border border-stone-200 bg-white p-0.5">
            {CATEGORIES.map(c => (
              <button
                key={c.key}
                type="button"
                onClick={() => setCategory(c.key)}
                className={cn(
                  'inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11.5px] transition',
                  category === c.key
                    ? 'bg-stone-800 text-white'
                    : 'text-stone-600 hover:bg-stone-100',
                )}
              >
                <c.icon className="h-3 w-3" />
                {c.label}
              </button>
            ))}
          </div>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setShowUnverified(v => !v)}
            title="切换显示未审核模板（默认仅显示 verified）"
          >
            {showUnverified ? (
              <Eye className="mr-1 h-3.5 w-3.5" />
            ) : (
              <EyeOff className="mr-1 h-3.5 w-3.5" />
            )}
            {showUnverified ? '显示全部' : '仅已审核'}
          </Button>
        </div>
      </header>

      {showUnverified && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 text-[11.5px] text-amber-700">
          ⚠️ 显示了未审核模板。这些可能由社区用户提交，未经官方核验；安装前请确认 spec_json 内容。
        </div>
      )}

      <SectionCard className="!p-3">
        {listQ.isLoading ? (
          <div className="py-12 text-center text-[12px] text-stone-400">
            加载中…
          </div>
        ) : (listQ.data ?? []).length === 0 ? (
          <div className="py-12 text-center text-[12px] text-stone-400">
            暂无模板
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {(listQ.data ?? []).map(t => (
              <TemplateCard
                key={String(t.id)}
                template={t}
                onInstall={() => installMut.mutate(t.id)}
                installing={installMut.isPending}
              />
            ))}
          </div>
        )}
      </SectionCard>
    </div>
  );
};

interface CardProps {
  template: AppTemplateItem;
  onInstall: () => void;
  installing: boolean;
}

const TemplateCard = ({ template, onInstall, installing }: CardProps) => {
  const catCls =
    CAT_COLORS[template.category] ?? 'bg-stone-100 text-stone-700';
  return (
    <div className="flex flex-col rounded-md border border-stone-200/70 bg-white p-3 shadow-sm transition hover:border-stone-300">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="truncate text-[13px] font-medium text-stone-900">
              {template.name}
            </span>
            {template.verified && (
              <CircleCheck
                className="h-3.5 w-3.5 shrink-0 text-emerald-600"
                aria-label="已审核"
              />
            )}
          </div>
          <span
            className={cn(
              'mt-1 inline-block rounded px-1.5 py-0.5 text-[10.5px] font-mono uppercase',
              catCls,
            )}
          >
            {template.category}
          </span>
        </div>
      </div>
      <p className="mb-3 line-clamp-3 min-h-[3em] text-[11.5px] text-stone-600">
        {template.description ?? <span className="text-stone-400">—</span>}
      </p>
      <div className="mt-auto flex items-center justify-between">
        <span className="font-mono text-[10.5px] text-stone-500">
          ⬇ {template.downloads}
        </span>
        <Button
          size="sm"
          onClick={onInstall}
          disabled={installing}
          title={
            !template.verified
              ? '此模板未审核；安装前请确认 spec'
              : '克隆模板到当前 workspace'
          }
        >
          <Download className="mr-1 h-3 w-3" />
          安装
        </Button>
      </div>
    </div>
  );
};
