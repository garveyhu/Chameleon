/** Workspace 配置抽屉 —— 编辑显示名 / 套餐（plan）。
 *
 * workspace_key 是身份标识不可改，只读展示；与模型/供应商/Channel 配置同一抽屉范式。
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/core/components/ui/sheet';
import { toast } from '@/core/lib/toast';
import { workspaceApi } from '@/system/workspaces/services/workspace';
import type {
  WorkspaceItem,
  WorkspacePlan,
} from '@/system/workspaces/types/workspace';
import { PLAN_OPTIONS } from '@/system/workspaces/types/workspace';

interface Props {
  workspace: WorkspaceItem | null;
  onClose: () => void;
}

const Field = ({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) => (
  <div className="space-y-1.5">
    <label className="text-[12px] font-medium text-stone-700">{label}</label>
    {children}
    {hint && <p className="text-[10.5px] leading-snug text-stone-500">{hint}</p>}
  </div>
);

export const WorkspaceConfigSheet = ({ workspace, onClose }: Props) => {
  const qc = useQueryClient();
  const [name, setName] = useState('');
  const [plan, setPlan] = useState<WorkspacePlan>('free');

  useEffect(() => {
    if (!workspace) return;
    setName(workspace.name);
    setPlan(workspace.plan);
  }, [workspace]);

  const saveMut = useMutation({
    mutationFn: () => workspaceApi.update(workspace!.id, { name, plan }),
    onSuccess: () => {
      toast.success('空间配置已保存');
      qc.invalidateQueries({ queryKey: ['workspaces'] });
      onClose();
    },
  });

  return (
    <Sheet open={!!workspace} onOpenChange={o => !o && onClose()}>
      <SheetContent>
        {workspace && (
          <>
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2">
                <span className="font-mono text-[15px]">{workspace.workspace_key}</span>
                <Badge variant="primary">{workspace.plan}</Badge>
              </SheetTitle>
              <SheetDescription>编辑空间显示名与套餐</SheetDescription>
            </SheetHeader>

            <SheetBody className="space-y-5">
              <Field label="workspace_key" hint="唯一标识，创建后不可更改">
                <div className="flex h-9 items-center rounded-md border border-stone-200 bg-stone-50 px-3 font-mono text-[12.5px] text-stone-500">
                  {workspace.workspace_key}
                </div>
              </Field>
              <Field label="显示名">
                <Input value={name} onChange={e => setName(e.target.value)} maxLength={128} />
              </Field>
              <Field label="套餐 plan" hint="影响该空间的默认配额与可用能力">
                <Select value={plan} onValueChange={v => setPlan(v as WorkspacePlan)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PLAN_OPTIONS.map(o => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
            </SheetBody>

            <SheetFooter>
              <Button variant="ghost" size="sm" onClick={onClose}>
                取消
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => saveMut.mutate()}
                disabled={saveMut.isPending || !name.trim()}
              >
                {saveMut.isPending ? '保存中…' : '保存配置'}
              </Button>
            </SheetFooter>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
};
