/** 文档站顶栏 —— 品牌 / 标题 / 通用 base / 返回控制台 */
import { ArrowUpRight, BookOpen } from 'lucide-react';
import { Link } from 'react-router-dom';

import { CopyButton } from './copy-button';

interface Props {
  baseUrl: string;
}

export const StationHeader = ({ baseUrl }: Props) => (
  <header className="flex h-14 flex-shrink-0 items-center gap-3 border-b border-stone-200/70 bg-[var(--color-paper)] px-5">
    <Link to="/dashboard" className="flex items-center gap-2.5">
      <img src="/logo-sm.png" alt="Chameleon" className="h-7 w-7 flex-shrink-0 object-contain" />
      <span className="text-[15px] font-semibold tracking-tight text-stone-800">Chameleon</span>
    </Link>
    <span className="h-5 w-px bg-stone-200" />
    <div className="flex items-center gap-2 text-[13.5px] font-semibold text-stone-700">
      <BookOpen className="h-4 w-4 text-stone-400" />
      API 文档
    </div>

    {/* 通用 base url */}
    <div className="ml-auto flex items-center gap-2">
      <div className="flex items-center gap-1.5 rounded-lg border border-stone-200 bg-white py-1 pr-1 pl-2.5 shadow-sm">
        <span className="shrink-0 text-[10.5px] text-stone-400">通用端点</span>
        <code className="max-w-[280px] truncate font-mono text-[12px] text-stone-700">{baseUrl}</code>
        <CopyButton text={baseUrl} />
      </div>
      <Link
        to="/dashboard"
        className="inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-[12.5px] text-stone-500 hover:bg-stone-100 hover:text-stone-800"
      >
        返回控制台 <ArrowUpRight className="h-3.5 w-3.5" />
      </Link>
    </div>
  </header>
);
