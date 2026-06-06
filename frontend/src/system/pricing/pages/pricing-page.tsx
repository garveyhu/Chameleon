/** 计费 / 价目管理 —— token（按 1K）+ 媒体（按张 / 按秒，视频分辨率分档）。
 *
 * 价目按时间版本：保存即新增当前生效版本，不改老行（cost 可重放）。币种 CNY 元。
 * 从「模型」页右上角进入。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Check, Coins, Loader2 } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { ProviderAvatar } from '@/core/components/common/provider-avatar';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import {
  type ModelPricingItem,
  pricingApi,
} from '@/system/pricing/services/pricing';

const KIND_META: Record<string, { label: string; hint: string }> = {
  chat: { label: '对话模型', hint: '按 token 计费（输入 / 输出，元 / 1K）' },
  embedding: { label: '向量模型', hint: '按 token 计费（仅输入计费）' },
  image: { label: '图片模型', hint: '按张计费（元 / 张）' },
  video: { label: '视频模型', hint: '按秒计费，分辨率分档（元 / 秒）' },
};
const KIND_ORDER = ['chat', 'embedding', 'image', 'video'];

/** 单个价格输入 + 单位后缀，紧凑右对齐 */
const PriceField = ({
  label,
  value,
  onChange,
  unit,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  unit: string;
}) => (
  <div className="flex items-center gap-2">
    <span className="w-7 shrink-0 text-right text-[11px] text-stone-400">{label}</span>
    <div className="relative">
      <input
        type="number"
        step="0.0001"
        min="0"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder="—"
        className="h-9 w-32 rounded-lg border border-stone-200 bg-white pr-12 pl-3 text-right font-mono text-[12.5px] text-stone-800 outline-none transition focus:border-primary-400 focus:ring-2 focus:ring-primary-100"
      />
      <span className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-[10px] text-stone-400">
        {unit}
      </span>
    </div>
  </div>
);

const SaveBtn = ({
  onClick,
  loading,
  dirty,
}: {
  onClick: () => void;
  loading: boolean;
  dirty: boolean;
}) => (
  <button
    type="button"
    onClick={onClick}
    disabled={loading || !dirty}
    className={cn(
      'inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-[12px] font-medium transition',
      dirty
        ? 'bg-primary-600 text-white hover:bg-primary-700'
        : 'cursor-default bg-stone-100 text-stone-400',
    )}
  >
    {loading ? (
      <Loader2 className="h-3.5 w-3.5 animate-spin" />
    ) : (
      <Check className="h-3.5 w-3.5" />
    )}
    保存
  </button>
);

/** 一行模型（左：头像+名；右：价格块 children） */
const ModelLine = ({
  item,
  children,
}: {
  item: ModelPricingItem;
  children: React.ReactNode;
}) => (
  <div className="group flex items-center gap-4 px-5 py-3.5 transition hover:bg-stone-50/60">
    <ProviderAvatar code={item.provider_code} />
    <div className="min-w-0 flex-1">
      <div className="truncate font-mono text-[13px] font-semibold text-stone-900">
        {item.model_code}
      </div>
      <div className="truncate text-[11px] text-stone-400">{item.provider_code || '?'}</div>
    </div>
    <div className="flex shrink-0 items-center gap-4">{children}</div>
  </div>
);

const useSave = (fn: () => Promise<unknown>) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      toast.success('价目已更新');
      qc.invalidateQueries({ queryKey: ['pricing', 'models'] });
    },
    onError: () => toast.error('保存失败'),
  });
};

const TokenLine = ({ item }: { item: ModelPricingItem }) => {
  const init = (v: number | null | undefined) => (v != null ? String(v) : '');
  const [prompt, setPrompt] = useState(() => init(item.prompt_per_1k));
  const [completion, setCompletion] = useState(() => init(item.completion_per_1k));
  const dirty = prompt !== init(item.prompt_per_1k) || completion !== init(item.completion_per_1k);
  const save = useSave(() =>
    pricingApi.setToken(item.model_code, Number(prompt || 0), Number(completion || 0)),
  );
  return (
    <ModelLine item={item}>
      <PriceField label="输入" value={prompt} onChange={setPrompt} unit="元/1K" />
      <PriceField label="输出" value={completion} onChange={setCompletion} unit="元/1K" />
      <SaveBtn onClick={() => save.mutate()} loading={save.isPending} dirty={dirty} />
    </ModelLine>
  );
};

const ImageLine = ({ item }: { item: ModelPricingItem }) => {
  const init = item.image_price != null ? String(item.image_price) : '';
  const [price, setPrice] = useState(() => init);
  const save = useSave(() => pricingApi.setMedia(item.model_code, 'image', Number(price || 0)));
  return (
    <ModelLine item={item}>
      <PriceField label="单价" value={price} onChange={setPrice} unit="元/张" />
      <SaveBtn onClick={() => save.mutate()} loading={save.isPending} dirty={price !== init} />
    </ModelLine>
  );
};

const VideoLine = ({ item }: { item: ModelPricingItem }) => {
  const init: Record<string, string> = {};
  for (const t of item.video_tiers ?? []) init[t.tier] = t.price != null ? String(t.price) : '';
  const [prices, setPrices] = useState<Record<string, string>>(() => ({ ...init }));
  const save = useMutation({
    mutationFn: (tier: string) =>
      pricingApi.setMedia(item.model_code, 'video_second', Number(prices[tier] || 0), tier),
    onSuccess: () => toast.success('价目已更新'),
    onError: () => toast.error('保存失败'),
  });
  const qc = useQueryClient();
  return (
    <ModelLine item={item}>
      <div className="flex flex-col gap-2">
        {(item.video_tiers ?? []).map(t => (
          <div key={t.tier} className="flex items-center gap-3">
            <span className="w-12 shrink-0 rounded bg-stone-100 px-1.5 py-0.5 text-center font-mono text-[10.5px] text-stone-500">
              {t.tier}
            </span>
            <PriceField
              label=""
              value={prices[t.tier] ?? ''}
              onChange={v => setPrices(p => ({ ...p, [t.tier]: v }))}
              unit="元/秒"
            />
            <SaveBtn
              onClick={() =>
                save.mutate(t.tier, {
                  onSuccess: () =>
                    qc.invalidateQueries({ queryKey: ['pricing', 'models'] }),
                })
              }
              loading={save.isPending}
              dirty={(prices[t.tier] ?? '') !== (init[t.tier] ?? '')}
            />
          </div>
        ))}
      </div>
    </ModelLine>
  );
};

export const PricingPage = () => {
  const { data, isLoading } = useQuery({
    queryKey: ['pricing', 'models'],
    queryFn: () => pricingApi.list(),
  });

  const groups = KIND_ORDER.map(kind => ({
    kind,
    items: (data ?? []).filter(m => m.kind === kind),
  })).filter(g => g.items.length > 0);

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <Link
        to="/models"
        className="mb-4 inline-flex items-center gap-1.5 text-[12px] text-stone-400 transition hover:text-stone-600"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> 返回模型
      </Link>

      <div className="mb-6 flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-50 text-primary-600">
          <Coins className="h-5 w-5" />
        </div>
        <div>
          <h1 className="text-[17px] font-semibold text-stone-900">计费 / 价目</h1>
          <p className="mt-0.5 text-[12.5px] text-stone-500">
            模型价目（人民币 元）。保存即新增生效版本，历史成本不变（可重放）。
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="py-16 text-center text-sm text-stone-400">加载中…</div>
      ) : (
        <div className="space-y-5">
          {groups.map(g => (
            <section
              key={g.kind}
              className="overflow-hidden rounded-2xl border border-stone-200 bg-[var(--color-paper)] shadow-sm"
            >
              <div className="flex items-baseline justify-between border-b border-stone-100 bg-stone-50/50 px-5 py-3">
                <span className="text-[13px] font-semibold text-stone-700">
                  {KIND_META[g.kind]?.label ?? g.kind}
                  <span className="ml-1.5 text-[11px] font-normal text-stone-400">
                    {g.items.length}
                  </span>
                </span>
                <span className="text-[11px] text-stone-400">{KIND_META[g.kind]?.hint}</span>
              </div>
              <div className="divide-y divide-stone-100">
                {g.items.map(item =>
                  item.kind === 'image' ? (
                    <ImageLine key={`${item.model_code}:${item.image_price}`} item={item} />
                  ) : item.kind === 'video' ? (
                    <VideoLine
                      key={`${item.model_code}:${(item.video_tiers ?? [])
                        .map(t => t.price)
                        .join(',')}`}
                      item={item}
                    />
                  ) : (
                    <TokenLine
                      key={`${item.model_code}:${item.prompt_per_1k}:${item.completion_per_1k}`}
                      item={item}
                    />
                  ),
                )}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
};
