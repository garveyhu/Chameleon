/** 编排方式（orchestration kind）推导 —— 由 agent 的 source + 关联 graph 的 kind 归一
 *
 * 语义（全站统一）：
 *   local              → code      代码
 *   graph + chatflow   → chatflow  对话编排
 *   graph + workflow   → workflow  流程编排
 *   dify / fastgpt / … → external  外部
 */

export type OrchestrationKind = 'code' | 'chatflow' | 'workflow' | 'external';

/** 由 source + graphKind 推导编排方式分类；无法识别返回 null。 */
export const resolveOrchestrationKind = (
  source: string | null | undefined,
  graphKind: string | null | undefined,
): OrchestrationKind | null => {
  if (source === 'local') return 'code';
  if (source === 'graph') return graphKind === 'workflow' ? 'workflow' : 'chatflow';
  if (source === 'dify' || source === 'fastgpt' || source === 'coze') return 'external';
  return null;
};
