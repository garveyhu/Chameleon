/** 指南页主区 —— 渲染 guide=true 的散文文档（能力概览 / 计费等，非端点）。 */
import { BookOpen } from 'lucide-react';

import type { EndpointSpec } from '@/api-docs/types/endpoint';

interface Props {
  guide: EndpointSpec;
}

export const GuideDetail = ({ guide }: Props) => (
  <div className="mx-auto max-w-3xl px-7 py-7">
    <div className="flex items-center gap-2.5">
      <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary-50 text-primary-600">
        <BookOpen className="h-5 w-5" />
      </span>
      <h1 className="text-[20px] font-semibold text-stone-900">{guide.title}</h1>
    </div>
    {guide.desc && (
      <p className="mt-2 text-[12.5px] leading-relaxed text-stone-500">{guide.desc}</p>
    )}
    <div className="mt-6 text-[13px] leading-relaxed text-stone-700">{guide.body}</div>
  </div>
);
