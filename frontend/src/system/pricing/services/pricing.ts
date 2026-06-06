import { get, post } from '@/core/lib/request';

export interface VideoTierPrice {
  tier: string;
  price: number | null;
}

export interface ModelPricingItem {
  model_code: string;
  kind: 'chat' | 'embedding' | 'rerank' | 'image' | 'video' | string;
  provider_code: string | null;
  currency: string;
  /** token 模型 */
  prompt_per_1k?: number | null;
  completion_per_1k?: number | null;
  /** 图片模型：每张价 */
  image_price?: number | null;
  /** 视频模型：各分辨率档每秒价 */
  video_tiers?: VideoTierPrice[];
}

export const pricingApi = {
  list: () => get<ModelPricingItem[]>('/v1/admin/pricing/models'),

  setToken: (model_code: string, prompt_per_1k: number, completion_per_1k: number) =>
    post<null>('/v1/admin/pricing/token/update', {
      model_code,
      prompt_per_1k,
      completion_per_1k,
    }),

  setMedia: (model_code: string, unit: string, price: number, tier = '') =>
    post<null>('/v1/admin/pricing/media/update', { model_code, unit, price, tier }),
};
