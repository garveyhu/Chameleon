/** ImageModelSelect —— 选一个「生图(image)」模型，值为 model.id（数值）
 *
 * 工作流 image_gen 节点与生图应用(comfyui agent)创建都按 model.id 绑定生图模型，
 * 故统一用本组件。数据源 GET /v1/admin/models?kind=image。
 */

import { useQuery } from '@tanstack/react-query';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { cn } from '@/core/lib/cn';
import { modelApi } from '@/system/models/services/model';

interface Props {
  /** 选中的 model.id；'' = 未选 */
  value: number | '';
  onChange: (id: number | '') => void;
  placeholder?: string;
  className?: string;
}

export const ImageModelSelect = ({
  value,
  onChange,
  placeholder = '选择生图模型',
  className,
}: Props) => {
  const q = useQuery({
    queryKey: ['models', 'image', 'select'],
    queryFn: () => modelApi.list({ kind: 'image' }),
    staleTime: 30_000,
  });
  const models = (q.data ?? []).filter(m => m.enabled);

  return (
    <Select
      value={value ? String(value) : undefined}
      onValueChange={v => onChange(v ? Number(v) : '')}
    >
      <SelectTrigger className={cn('h-7 text-[12px]', className)}>
        <SelectValue placeholder={q.isLoading ? '加载中…' : placeholder} />
      </SelectTrigger>
      <SelectContent>
        {models.map(m => (
          <SelectItem key={m.id} value={String(m.id)} className="text-[12px]">
            <span className="font-mono">{m.code}</span>
            {m.provider_code ? (
              <span className="ml-1.5 text-[10px] text-stone-400">
                {m.provider_code}
              </span>
            ) : null}
          </SelectItem>
        ))}
        {!q.isLoading && models.length === 0 ? (
          <div className="px-2 py-1.5 text-[11px] text-stone-400">
            暂无生图模型，请先在「模型」页添加 image 模型
          </div>
        ) : null}
      </SelectContent>
    </Select>
  );
};
