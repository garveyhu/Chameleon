/** 通用 DOM 导出工具：把元素截成 PNG / 下载文本文件。供 trace、运行对比等复用。 */

import { toPng } from 'html-to-image';

/** 触发浏览器下载一个文本文件（默认 markdown）。 */
export const downloadText = (
  filename: string,
  content: string,
  mime = 'text/markdown;charset=utf-8',
): void => {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
};

interface ExportImageOptions {
  /** 四周留白 px（默认 28） */
  pad?: number;
  /** 设备像素比，越高越清晰但越慢（默认 2；大 DOM 建议 1.5） */
  pixelRatio?: number;
  /** 跳过 @font-face web 字体内联——大 DOM 提速关键（中文走系统字体不受影响） */
  skipFonts?: boolean;
}

/** 把 DOM 元素截成 PNG 下载（默认 2x，白底，四周留白）。
 *
 * 关键：画布显式扩出 padding（content-box + 锁定内容宽度），否则给节点加 padding 会把
 * 内容挤进更窄的盒子导致右侧截断。
 *
 * 大 DOM（长表格 / 长文）建议传 pixelRatio:1.5 + skipFonts:true 提速——html-to-image
 * 的耗时主要在逐节点取计算样式与字体内联，节点多时会很慢。
 */
export const exportImage = async (
  el: HTMLElement,
  filename: string,
  opts: ExportImageOptions = {},
): Promise<void> => {
  const { pad = 28, pixelRatio = 2, skipFonts = false } = opts;
  // 向上取整避免分数像素截断；overflow:visible 防止克隆体在离屏渲染时出现纵向滚动条
  // 吃掉右侧宽度导致内容截断。
  const w = Math.ceil(el.scrollWidth);
  const h = Math.ceil(el.scrollHeight);
  const dataUrl = await toPng(el, {
    backgroundColor: '#ffffff',
    pixelRatio,
    skipFonts,
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
