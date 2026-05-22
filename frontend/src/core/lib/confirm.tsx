/** 命令式 confirm()，返回 Promise<boolean>。替换原生 window.confirm。
 *
 * 用法：
 *   import { confirm } from '@/core/lib/confirm'
 *   if (await confirm({ title: '删除文档?', description: '将同步清理切块与对象存储。', danger: true })) {
 *     deleteMut.mutate(id)
 *   }
 *
 * 实现：动态挂一个 React root 到 document.body，render ConfirmDialog；
 * 用户点确认 / 取消 / ESC / 点遮罩 → resolve(true/false) → 卸载 root。
 */

import { createRoot } from 'react-dom/client';

import { ConfirmDialog } from '@/core/components/common/confirm-dialog';

interface ConfirmOptions {
  title: string;
  description?: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
}

export function confirm(opts: ConfirmOptions): Promise<boolean> {
  return new Promise(resolve => {
    const host = document.createElement('div');
    document.body.appendChild(host);
    const root = createRoot(host);

    const close = (result: boolean) => {
      // 等动画跑完再卸载，避免 Radix close 时 flash
      setTimeout(() => {
        root.unmount();
        if (host.parentNode) host.parentNode.removeChild(host);
      }, 200);
      resolve(result);
    };

    root.render(
      <ConfirmDialog
        open
        title={opts.title}
        description={opts.description}
        confirmText={opts.confirmText ?? '确认'}
        cancelText={opts.cancelText ?? '取消'}
        variant={opts.danger ? 'danger' : 'default'}
        onConfirm={() => close(true)}
        onCancel={() => close(false)}
      />,
    );
  });
}
