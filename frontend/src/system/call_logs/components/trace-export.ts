/** Trace 一键导出：结构化文字（Markdown，带元信息）+ 图片（PNG）。
 *  方便排查时把溯源情况整段复制 / 截图发出去。 */

import { toPng } from 'html-to-image';

import { formatCost, formatDateTime, formatDurationMs } from '@/core/lib/format';
import {
  extractMessages,
  groupInput,
  INPUT_TEXT_KEYS,
  OUTPUT_TEXT_KEYS,
  type Payload,
  pickText,
  ROLE_LABEL,
} from '@/system/call_logs/components/trace-parse';
import type { CallLogDetail } from '@/system/call_logs/types/call-log';

/** 元信息 + 输入(系统/参考资料/历史/本轮) + 输出 → Markdown 文本 */
export const buildTraceText = (node: CallLogDetail): string => {
  const L: string[] = [];
  L.push(`# Trace 溯源 · ${node.agent_key}`);
  L.push('');
  L.push('## 元信息');
  L.push(`- 时间: ${formatDateTime(node.created_at)}`);
  L.push(`- 请求: ${node.request_id}`);
  if (node.session_id) L.push(`- 会话: ${node.session_id}`);
  L.push(`- 渠道: ${node.channel ?? '—'}`);
  L.push(`- 模型: ${node.model_code ?? '—'}`);
  L.push(`- 状态: ${node.success ? '成功' : `失败 ${node.code}`}`);
  L.push(`- 耗时: ${formatDurationMs(node.duration_ms)}`);
  L.push(
    `- Token: ${node.total_tokens ?? '—'} (↑${node.prompt_tokens ?? 0} ↓${node.completion_tokens ?? 0})`,
  );
  L.push(`- 成本: ${node.cost_usd != null ? formatCost(node.cost_usd) : '—'}`);
  if (node.error_message) L.push(`- 错误: ${node.error_message}`);
  L.push('');

  const reqPayload = node.request_payload as Payload;
  const msgs = extractMessages(reqPayload, INPUT_TEXT_KEYS);
  L.push('## 输入');
  if (msgs) {
    const { system, history, current } = groupInput(msgs);
    for (const s of system) {
      L.push('### 系统');
      L.push(s.content);
      L.push('');
    }
    if (history.length) {
      L.push('### 历史对话');
      history.forEach(m => L.push(`**${ROLE_LABEL[m.role] ?? m.role}**：${m.content}`));
      L.push('');
    }
    if (current) {
      L.push('### 本轮输入');
      L.push(current.content);
      L.push('');
    }
  } else {
    L.push('```json');
    L.push(JSON.stringify(reqPayload ?? {}, null, 2));
    L.push('```');
    L.push('');
  }

  L.push('## 输出');
  const out = pickText(node.response_payload as Payload, OUTPUT_TEXT_KEYS);
  if (out) {
    L.push(out);
  } else {
    L.push('```json');
    L.push(JSON.stringify(node.response_payload ?? {}, null, 2));
    L.push('```');
  }
  L.push('');
  return L.join('\n');
};

/** 触发浏览器下载一个文本文件 */
export const downloadText = (filename: string, content: string): void => {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
};

/** 把 DOM 元素截成 PNG 下载（2x，白底，四周留白）
 *
 * 关键：画布显式扩出 padding（content-box + 锁定内容宽度），否则给节点加 padding 会把
 * 内容挤进更窄的盒子导致右侧截断。
 */
export const exportImage = async (el: HTMLElement, filename: string): Promise<void> => {
  const pad = 28;
  // 向上取整避免分数像素截断；overflow:visible 防止克隆体在离屏渲染时出现纵向滚动条
  // 吃掉右侧宽度导致内容截断。
  const w = Math.ceil(el.scrollWidth);
  const h = Math.ceil(el.scrollHeight);
  const dataUrl = await toPng(el, {
    backgroundColor: '#ffffff',
    pixelRatio: 2,
    cacheBust: true,
    width: w + pad * 2,
    height: h + pad * 2,
    style: {
      boxSizing: 'content-box',
      width: `${w}px`,
      height: `${h}px`,
      padding: `${pad}px`,
      margin: '0',
      overflow: 'visible',
    },
  });
  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = filename;
  a.click();
};
