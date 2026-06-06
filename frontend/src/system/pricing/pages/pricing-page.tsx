/** 计费 / 价目管理 —— token（按 1K）+ 媒体（按张 / 按秒，视频分辨率分档）。
 *
 * 价目按时间版本：保存即新增当前生效版本，不改老行（cost 可重放）。币种 CNY 元。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { ProviderAvatar } from '@/core/components/common/provider-avatar';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { toast } from '@/core/lib/toast';
import {
  type ModelPricingItem,
  pricingApi,
} from '@/system/pricing/services/pricing';

const KIND_LABEL: Record<string, string> = {
  chat: '对话模型',
  embedding: '向量模型',
  image: '图片模型',
  video: '视频模型',
};
const KIND_ORDER = ['chat', 'embedding', 'image', 'video'];

const PriceInput = ({
  value,
  onChange,
  suffix,
}: {
  value: string;
  onChange: (v: string) => void;
  suffix: string;
}) => (
  <div className="flex items-center gap-1">
    <Input
      type="number"
      step="0.0001"
      min="0"
      value={value}
      onChange={e => onChange(e.target.value)}
      className="h-8 w-28 text-[12.5px]"
    />
    <span className="text-[11px] text-stone-400">{suffix}</span>
  </div>
);

const TokenRow = ({ item }: { item: ModelPricingItem }) => {
  const qc = useQueryClient();
  // 惰性初始化（避免 set-state-in-effect）；保存后父级按价值变 key 重挂以刷新
  const [prompt, setPrompt] = useState(() =>
    item.prompt_per_1k != null ? String(item.prompt_per_1k) : '',
  );
  const [completion, setCompletion] = useState(() =>
    item.completion_per_1k != null ? String(item.completion_per_1k) : '',
  );

  const save = useMutation({
    mutationFn: () =>
      pricingApi.setToken(item.model_code, Number(prompt || 0), Number(completion || 0)),
    onSuccess: () => {
      toast.success('价目已更新');
      qc.invalidateQueries({ queryKey: ['pricing', 'models'] });
    },
    onError: () => toast.error('保存失败'),
  });

  return (
    <Row item={item}>
      <div className="flex flex-wrap items-center gap-4">
        <Field label="输入">
          <PriceInput value={prompt} onChange={setPrompt} suffix="元 / 1K tokens" />
        </Field>
        <Field label="输出">
          <PriceInput value={completion} onChange={setCompletion} suffix="元 / 1K tokens" />
        </Field>
        <SaveBtn onClick={() => save.mutate()} loading={save.isPending} />
      </div>
    </Row>
  );
};

const ImageRow = ({ item }: { item: ModelPricingItem }) => {
  const qc = useQueryClient();
  const [price, setPrice] = useState(() =>
    item.image_price != null ? String(item.image_price) : '',
  );

  const save = useMutation({
    mutationFn: () => pricingApi.setMedia(item.model_code, 'image', Number(price || 0)),
    onSuccess: () => {
      toast.success('价目已更新');
      qc.invalidateQueries({ queryKey: ['pricing', 'models'] });
    },
    onError: () => toast.error('保存失败'),
  });

  return (
    <Row item={item}>
      <div className="flex flex-wrap items-center gap-4">
        <Field label="单价">
          <PriceInput value={price} onChange={setPrice} suffix="元 / 张" />
        </Field>
        <SaveBtn onClick={() => save.mutate()} loading={save.isPending} />
      </div>
    </Row>
  );
};

const VideoRow = ({ item }: { item: ModelPricingItem }) => {
  const qc = useQueryClient();
  const [prices, setPrices] = useState<Record<string, string>>(() => {
    const next: Record<string, string> = {};
    for (const t of item.video_tiers ?? [])
      next[t.tier] = t.price != null ? String(t.price) : '';
    return next;
  });

  const save = useMutation({
    mutationFn: (tier: string) =>
      pricingApi.setMedia(item.model_code, 'video_second', Number(prices[tier] || 0), tier),
    onSuccess: () => {
      toast.success('价目已更新');
      qc.invalidateQueries({ queryKey: ['pricing', 'models'] });
    },
    onError: () => toast.error('保存失败'),
  });

  return (
    <Row item={item}>
      <div className="flex flex-col gap-2">
        {(item.video_tiers ?? []).map(t => (
          <div key={t.tier} className="flex flex-wrap items-center gap-3">
            <Field label={t.tier}>
              <PriceInput
                value={prices[t.tier] ?? ''}
                onChange={v => setPrices(p => ({ ...p, [t.tier]: v }))}
                suffix="元 / 秒"
              />
            </Field>
            <SaveBtn onClick={() => save.mutate(t.tier)} loading={save.isPending} />
          </div>
        ))}
      </div>
    </Row>
  );
};

const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="flex items-center gap-2">
    <span className="w-10 text-[12px] text-stone-500">{label}</span>
    {children}
  </div>
);

const SaveBtn = ({ onClick, loading }: { onClick: () => void; loading: boolean }) => (
  <Button size="sm" variant="outline" onClick={onClick} disabled={loading} className="h-8">
    {loading ? '保存中…' : '保存'}
  </Button>
);

const Row = ({ item, children }: { item: ModelPricingItem; children: React.ReactNode }) => (
  <div className="flex items-start justify-between gap-4 rounded-xl border border-stone-200 bg-[var(--color-paper)] p-3.5">
    <div className="flex min-w-0 items-center gap-2.5">
      <ProviderAvatar code={item.provider_code} />
      <div className="min-w-0">
        <div className="truncate font-mono text-[13px] font-semibold text-stone-900">
          {item.model_code}
        </div>
        <div className="text-[11px] text-stone-400">{item.provider_code || '?'}</div>
      </div>
    </div>
    {children}
  </div>
);

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
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-4">
        <h1 className="text-lg font-semibold text-stone-900">计费 / 价目</h1>
        <p className="mt-0.5 text-[12.5px] text-stone-500">
          模型价目（人民币 元）。保存即新增生效版本，历史成本不变（可重放）。
        </p>
      </div>

      {isLoading ? (
        <div className="py-12 text-center text-sm text-stone-400">加载中…</div>
      ) : (
        <div className="space-y-6">
          {groups.map(g => (
            <section key={g.kind}>
              <div className="mb-2 text-[12.5px] font-medium text-stone-600">
                {KIND_LABEL[g.kind] ?? g.kind}
                <span className="ml-1.5 text-stone-400">{g.items.length}</span>
              </div>
              <div className="space-y-2">
                {g.items.map(item =>
                  item.kind === 'image' ? (
                    <ImageRow
                      key={`${item.model_code}:${item.image_price}`}
                      item={item}
                    />
                  ) : item.kind === 'video' ? (
                    <VideoRow
                      key={`${item.model_code}:${(item.video_tiers ?? [])
                        .map(t => t.price)
                        .join(',')}`}
                      item={item}
                    />
                  ) : (
                    <TokenRow
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
