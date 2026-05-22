/** ColumnHeader —— 表头 + hover ? hint 图标 */

import { HelpCircle } from 'lucide-react';
import * as React from 'react';

import { Tooltip } from '@/core/components/ui/tooltip';

interface ColumnHeaderProps {
  title: React.ReactNode;
  hint?: React.ReactNode;
}

export const ColumnHeader: React.FC<ColumnHeaderProps> = ({ title, hint }) => (
  <span className="inline-flex items-center gap-1">
    {title}
    {hint ? (
      <Tooltip content={hint}>
        <HelpCircle
          className="h-3 w-3 cursor-help text-stone-300 hover:text-stone-500"
          strokeWidth={1.75}
        />
      </Tooltip>
    ) : null}
  </span>
);
