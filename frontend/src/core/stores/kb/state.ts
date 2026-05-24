/** kb store —— state slice：检索测试（hit-test）的客户端态
 *
 * 检索请求本身走 react-query mutation；本 store 持 query 参数 + 结果 + 选中态，
 * 供 D5 三栏（参数 / chunk 列表 / 原文）共享。
 */

import type { EntityId } from '@/core/types/api';
import type { RecallMode, SearchHitItem } from '@/system/kbs/types/kb';

export interface KbHitTestState {
  query: string;
  topK: number;
  mode: RecallMode;
  /** 逗号分隔的标签过滤原始输入 */
  tags: string;
  /** 是否开启 multi-query 扩展（依赖 Agent B 后端，先占位） */
  multiQuery: boolean;
  hits: SearchHitItem[];
  /** 当前选中的命中 chunk_id（三栏右侧看原文） */
  selectedChunkId: EntityId | null;
}

export function createInitialKbState(): KbHitTestState {
  return {
    query: '',
    topK: 5,
    mode: 'vector',
    tags: '',
    multiQuery: false,
    hits: [],
    selectedChunkId: null,
  };
}
