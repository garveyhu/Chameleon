/** 端点详情主区（中栏）—— Method / path / desc / 鉴权 / 参数表 / 响应字段
 *
 * 单一职责：把 EndpointSpec 渲染成可读的左半页文档。
 * 右侧 cURL / 响应示例由 ExamplePane 单独承担。
 */
import { PlayCircle } from 'lucide-react';

import type { EndpointSpec } from '@/api-docs/types/endpoint';
import { Button } from '@/core/components/ui/button';

import { AuthBlock } from './auth-block';
import { CopyButton } from './copy-button';
import { MethodPill } from './method-pill';
import { ParamTable } from './param-table';

interface Props {
  endpoint: EndpointSpec;
}

export const EndpointDetail = ({ endpoint }: Props) => {
  return (
    <div className="mx-auto max-w-3xl px-7 py-7">
      {/* 标题 + 试一试 */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-[20px] font-semibold text-stone-900">{endpoint.title}</h1>
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-stone-500">{endpoint.desc}</p>
        </div>
        <Button
          size="sm"
          variant="outline"
          disabled
          title="即将上线"
          className="shrink-0 gap-1"
        >
          <PlayCircle className="h-3.5 w-3.5" /> 试一试
        </Button>
      </div>

      {/* Method + Path 行 */}
      <div className="mt-4 flex items-center gap-2 rounded-xl border border-stone-200 bg-stone-50/70 px-3 py-2">
        <MethodPill method={endpoint.method} />
        <code className="min-w-0 flex-1 truncate font-mono text-[13px] text-stone-800">{endpoint.path}</code>
        <CopyButton text={endpoint.path} />
      </div>

      <AuthBlock auth={endpoint.auth} />

      {endpoint.pathParams && <ParamTable title="Path 参数" params={endpoint.pathParams} />}
      {endpoint.queryParams && <ParamTable title="Query 参数" params={endpoint.queryParams} />}
      {endpoint.bodyParams && <ParamTable title="Body 参数" params={endpoint.bodyParams} />}

      {/* 响应概览 */}
      <div className="mt-7">
        <h3 className="mb-2 text-[12.5px] font-semibold tracking-[0.04em] text-stone-500 uppercase">
          响应
        </h3>
        <div className="space-y-2">
          {endpoint.responses.map((r, i) => (
            <div
              key={i}
              className="flex items-baseline gap-3 rounded-lg border border-stone-200 bg-white px-3 py-2"
            >
              <span className="rounded bg-emerald-50 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-emerald-700">
                {r.code}
              </span>
              <span className="text-[12.5px] font-medium text-stone-700">
                {r.name ?? `${r.code} - application/json`}
              </span>
              {r.desc && <span className="flex-1 text-[12px] text-stone-500">{r.desc}</span>}
            </div>
          ))}
        </div>
        <p className="mt-2 text-[11.5px] text-stone-400">
          完整响应示例见右侧「示例」面板。
        </p>
      </div>
    </div>
  );
};
