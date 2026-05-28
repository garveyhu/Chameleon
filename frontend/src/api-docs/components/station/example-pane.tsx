/** 右侧示例栏 —— cURL + 各响应示例
 *
 * 单一职责：把 endpoint.cURL 与 endpoint.responses[*].example 渲染成 sticky 代码栈。
 */
import type { EndpointSpec } from '@/api-docs/types/endpoint';

import { CodeBlock } from './code-block';

interface Props {
  endpoint: EndpointSpec;
  baseUrl: string;
}

const formatExample = (ex: unknown): string => {
  if (ex == null) return '';
  if (typeof ex === 'string') return ex;
  try {
    return JSON.stringify(ex, null, 2);
  } catch {
    return String(ex);
  }
};

export const ExamplePane = ({ endpoint, baseUrl }: Props) => {
  const curl = endpoint.cURL.replaceAll('{BASE}', baseUrl);

  return (
    <aside className="hidden h-full w-[26rem] shrink-0 overflow-y-auto border-l border-stone-200/70 bg-stone-50/50 px-5 py-6 lg:block">
      <div className="space-y-5">
        <section>
          <h3 className="mb-2 text-[12.5px] font-semibold tracking-[0.04em] text-stone-500 uppercase">
            请求示例
          </h3>
          <CodeBlock text={curl} label="cURL" />
        </section>

        {endpoint.responses.map((r, i) => {
          const text = formatExample(r.example);
          if (!text) return null;
          return (
            <section key={i}>
              <h3 className="mb-2 text-[12.5px] font-semibold tracking-[0.04em] text-stone-500 uppercase">
                {r.name ?? `${r.code} 响应`}
              </h3>
              <CodeBlock
                text={text}
                label={typeof r.example === 'string' ? 'SSE' : 'JSON'}
              />
            </section>
          );
        })}
      </div>
    </aside>
  );
};
