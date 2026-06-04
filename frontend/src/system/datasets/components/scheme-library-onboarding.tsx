/** 评分方案库 onboarding —— 讲清「评分方案是什么」「怎么用」。
 *
 * 空态时铺满引导卡；已有方案时收为一条 slim 提示，不抢版面。
 */

import { Lightbulb, Ruler, Workflow } from 'lucide-react';
import type { ReactNode } from 'react';

interface SchemeLibraryOnboardingProps {
  total: number;
  loading: boolean;
}

export const SchemeLibraryOnboarding = ({
  total,
  loading,
}: SchemeLibraryOnboardingProps) => {
  if (loading) return null;

  if (total === 0) {
    return (
      <div className="mb-4 rounded-xl border border-stone-200 bg-gradient-to-br from-stone-50 to-white p-5">
        <div className="mb-3 flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary-50 text-primary-600">
            <Lightbulb className="h-4 w-4" />
          </span>
          <h3 className="text-[14px] font-medium text-stone-900">
            什么是评分方案？
          </h3>
        </div>
        <p className="mb-4 max-w-2xl text-[12.5px] leading-relaxed text-stone-600">
          评分方案是一套可复用的「如何给评测结果打分」的配置 ——
          把多个评分指标（准确率 / 相关性 / 自定义 judge 等）按权重和阈值打包成一个命名方案。
          建好一次，之后在「新建评估」和「定时任务」里直接选它，不必每次重配 judge。
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Step
            icon={<Ruler className="h-3.5 w-3.5" />}
            title="1 · 建方案"
            desc="点右上「新建方案」，配置一组带权重 / 阈值的评分指标。"
          />
          <Step
            icon={<Workflow className="h-3.5 w-3.5" />}
            title="2 · 用方案"
            desc="在「新建评估」或「定时任务」里选这个方案，立即跑或周期跑。"
          />
        </div>
      </div>
    );
  }

  return (
    <div className="mb-3 flex items-start gap-2 rounded-lg border border-stone-200/70 bg-stone-50/50 px-3 py-2 text-[11.5px] leading-relaxed text-stone-500">
      <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary-500" />
      <span>
        评分方案 = 复用的多指标 / judge 打分配置。建好后在「新建评估」与「定时任务」里选它打分；
        改方案自动升版本，已绑定任务按 freeze 版本不受影响。
      </span>
    </div>
  );
};

const Step = ({
  icon,
  title,
  desc,
}: {
  icon: ReactNode;
  title: string;
  desc: string;
}) => (
  <div className="rounded-lg border border-stone-200/70 bg-white p-3">
    <div className="mb-1 flex items-center gap-1.5 text-[12px] font-medium text-stone-800">
      <span className="text-primary-500">{icon}</span>
      {title}
    </div>
    <p className="text-[11.5px] leading-snug text-stone-500">{desc}</p>
  </div>
);
