/** PageHeader —— 紧凑标题（waveflow 风格）
 *
 * 留作兼容；新页推荐把 title 嵌进 TableToolbar，省一层 padding。
 */

import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
}

export const PageHeader = ({ title, description, actions }: PageHeaderProps) => (
  <div className="mb-4 flex items-start justify-between gap-4">
    <div>
      <h1 className="text-[15px] font-semibold tracking-tight text-stone-900">{title}</h1>
      {description && <p className="mt-0.5 text-[12px] text-stone-500">{description}</p>}
    </div>
    {actions && <div className="flex items-center gap-1.5">{actions}</div>}
  </div>
);
