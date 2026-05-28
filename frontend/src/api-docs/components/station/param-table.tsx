/** 参数表 —— Path / Query / Body 通用 */
import type { ParamSpec } from '@/api-docs/types/endpoint';

interface Props {
  title: string;
  params: ParamSpec[];
}

const fmtDefault = (v: ParamSpec['default']): string => {
  if (v === null) return 'null';
  if (typeof v === 'string') return v;
  return String(v);
};

export const ParamTable = ({ title, params }: Props) => {
  if (params.length === 0) return null;
  return (
    <div className="mt-4">
      <h3 className="mb-2 text-[12.5px] font-semibold tracking-[0.04em] text-stone-500 uppercase">
        {title}
      </h3>
      <div className="overflow-hidden rounded-lg border border-stone-200">
        <table className="w-full text-left text-[12.5px] text-stone-700">
          <thead className="bg-stone-50 text-[11.5px] font-semibold text-stone-500">
            <tr>
              <th className="px-3 py-2 font-semibold whitespace-nowrap">参数</th>
              <th className="px-3 py-2 font-semibold whitespace-nowrap">类型</th>
              <th className="w-16 px-3 py-2 font-semibold whitespace-nowrap">必填</th>
              <th className="px-3 py-2 font-semibold whitespace-nowrap">默认值</th>
              <th className="px-3 py-2 font-semibold whitespace-nowrap">说明</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-200/70">
            {params.map(p => (
              <tr key={p.name} className="align-top">
                <td className="px-3 py-2 font-mono text-[12px] whitespace-nowrap text-stone-800">{p.name}</td>
                <td className="px-3 py-2 font-mono text-[11.5px] whitespace-nowrap text-stone-500">{p.type}</td>
                <td className="px-3 py-2 whitespace-nowrap">
                  {p.required ? (
                    <span className="inline-block rounded bg-rose-50 px-1.5 py-0.5 text-[10.5px] font-medium text-rose-600 whitespace-nowrap">
                      必填
                    </span>
                  ) : (
                    <span className="text-[11px] text-stone-400">可选</span>
                  )}
                </td>
                <td className="px-3 py-2 font-mono text-[11.5px] whitespace-nowrap text-stone-500">
                  {p.default !== undefined ? fmtDefault(p.default) : '—'}
                </td>
                <td className="px-3 py-2 text-[12px] leading-relaxed text-stone-600">{p.desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
