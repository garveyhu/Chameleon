/** trace store —— state slice：trace 详情 / Gantt 的视图态
 *
 * 纯客户端视图态（选中 / hover / 折叠 / 缩放）；trace tree 本身走 react-query。
 * 切换 trace 时调 reset() 清空。
 */

export interface TraceViewState {
  /** 当前选中的节点 request_id（详情面板 + 高亮） */
  selectedId: string | null;
  /** hover 中的节点 request_id（Gantt / 树联动高亮） */
  hoveredId: string | null;
  /** 折叠的节点 request_id 集合（值为 true 即折叠） */
  collapsed: Record<string, boolean>;
  /** Gantt 缩放系数（1 = 适配宽度；>1 放大时间轴） */
  ganttZoom: number;
}

export function createInitialTraceState(): TraceViewState {
  return {
    selectedId: null,
    hoveredId: null,
    collapsed: {},
    ganttZoom: 1,
  };
}
