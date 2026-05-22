/** Schema 调试页 —— 渲染任意注册过的 JSON Schema，验证表单效果
 *
 * 路径：/dev/schemas
 * 用途：
 *   - 开发者验证新注册 schema 渲染效果
 *   - 插件 / Workflow 节点作者预览自家 schema 的表单形态
 *   - 调试 inline_refs / placeholder / enumNames 等 UI hint
 */

import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { SectionCard } from '@/core/components/table';
import { Button } from '@/core/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { JSONSchemaForm } from '@/core/components/form';
import { schemaApi } from '@/core/services/schema';

export const DevSchemasPage = () => {
  const [picked, setPicked] = useState<string>('');
  const [value, setValue] = useState<unknown>(undefined);
  const [inlineRefs, setInlineRefs] = useState(true);

  const listQ = useQuery({
    queryKey: ['schemas', 'list'],
    queryFn: () => schemaApi.list(),
  });

  const schemaQ = useQuery({
    queryKey: ['schemas', 'get', picked, inlineRefs],
    queryFn: () => schemaApi.get(picked, { inlineRefs }),
    enabled: !!picked,
  });

  const items = useMemo(() => listQ.data ?? [], [listQ.data]);
  const grouped = useMemo(() => {
    const m = new Map<string, typeof items>();
    for (const it of items) {
      const ns = it.name.split('.')[0];
      const arr = m.get(ns) ?? [];
      arr.push(it);
      m.set(ns, arr);
    }
    return Array.from(m.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [items]);

  return (
    <div className="grid grid-cols-2 gap-4">
      <SectionCard>
        <div className="space-y-3 p-4">
          <div className="flex items-baseline justify-between">
            <h3 className="text-[13px] font-semibold text-stone-900">
              Schema 调试
            </h3>
            <span className="text-[11px] text-stone-500">
              {items.length} 个已注册
            </span>
          </div>
          <div className="space-y-1.5">
            <label className="text-[12px] text-stone-600">选择 schema</label>
            <Select
              value={picked}
              onValueChange={v => {
                setPicked(v);
                setValue(undefined);
              }}
              disabled={listQ.isLoading}
            >
              <SelectTrigger>
                <SelectValue placeholder="选一个 schema…" />
              </SelectTrigger>
              <SelectContent>
                {grouped.map(([ns, list]) => (
                  <div key={ns}>
                    <div className="px-2 py-1 text-[10.5px] uppercase text-stone-400">
                      {ns}
                    </div>
                    {list.map(it => (
                      <SelectItem key={it.name} value={it.name}>
                        {it.name}
                      </SelectItem>
                    ))}
                  </div>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2 text-[12px]">
            <input
              type="checkbox"
              id="inline-refs"
              checked={inlineRefs}
              onChange={e => setInlineRefs(e.target.checked)}
              className="h-3.5 w-3.5"
            />
            <label htmlFor="inline-refs" className="text-stone-600">
              inline_refs（把 $defs / $ref 内联展开）
            </label>
          </div>

          <div className="border-t border-stone-200/60 pt-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[12px] font-medium text-stone-700">
                表单渲染
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setValue(undefined)}
                disabled={!picked}
              >
                清空
              </Button>
            </div>
            {schemaQ.isLoading ? (
              <div className="text-[12px] text-stone-400">加载 schema…</div>
            ) : schemaQ.data ? (
              <JSONSchemaForm
                schema={schemaQ.data}
                value={value}
                onChange={setValue}
              />
            ) : (
              <div className="rounded-md border border-stone-200/70 bg-stone-50/40 px-3 py-6 text-center text-[12px] text-stone-400">
                选一个 schema 查看渲染效果
              </div>
            )}
          </div>
        </div>
      </SectionCard>

      <SectionCard>
        <div className="space-y-3 p-4">
          <h3 className="text-[13px] font-semibold text-stone-900">
            实时输出（提交给后端的 JSON）
          </h3>
          <pre className="max-h-[260px] overflow-auto rounded-md border border-stone-200/60 bg-stone-50/60 p-3 font-mono text-[11.5px] leading-relaxed text-stone-800">
{JSON.stringify(value, null, 2) || '// 等待表单输入…'}
          </pre>
          <h3 className="pt-2 text-[13px] font-semibold text-stone-900">
            原始 schema
          </h3>
          <pre className="max-h-[260px] overflow-auto rounded-md border border-stone-200/60 bg-stone-50/60 p-3 font-mono text-[11px] leading-relaxed text-stone-800">
{schemaQ.data
  ? JSON.stringify(schemaQ.data, null, 2)
  : '// 选 schema 后显示…'}
          </pre>
        </div>
      </SectionCard>
    </div>
  );
};
