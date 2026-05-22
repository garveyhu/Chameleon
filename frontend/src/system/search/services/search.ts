/** 全站搜索 API */

import { get } from '@/core/lib/request';

export type SearchType =
  | 'agent'
  | 'model'
  | 'provider'
  | 'kb'
  | 'app'
  | 'user'
  | 'embed_config';

export interface SearchResult {
  type: SearchType;
  id: number;
  title: string;
  snippet: string;
  url: string;
  icon: string;
}

export interface SearchResponse {
  results: SearchResult[];
}

export const searchApi = {
  search: (q: string, limit = 20) =>
    get<SearchResponse>('/v1/admin/search', { params: { q, limit } }),
};
