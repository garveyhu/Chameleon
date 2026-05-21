/** 角色管理页 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, ShieldCheck, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

import { ConfirmDialog } from '@/core/components/common/confirm-dialog';
import {
  DataTable,
  type DataTableColumn,
  SectionCard,
  TableToolbar,
} from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { Label } from '@/core/components/ui/label';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/core/components/ui/sheet';
import { Textarea } from '@/core/components/ui/textarea';
import { permissionApi, roleApi } from '@/system/roles/services/role';
import type { RoleItem } from '@/system/roles/types/role';

export const RolesPage = () => {
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [permRole, setPermRole] = useState<RoleItem | null>(null);
  const [delRole, setDelRole] = useState<RoleItem | null>(null);

  const listQ = useQuery({ queryKey: ['roles'], queryFn: roleApi.list });

  const createMut = useMutation({
    mutationFn: roleApi.create,
    onSuccess: () => {
      toast.success('角色已创建');
      qc.invalidateQueries({ queryKey: ['roles'] });
      setCreateOpen(false);
    },
  });

  const delMut = useMutation({
    mutationFn: roleApi.delete,
    onSuccess: () => {
      toast.success('角色已删除');
      qc.invalidateQueries({ queryKey: ['roles'] });
      setDelRole(null);
    },
  });

  const columns: DataTableColumn<RoleItem>[] = [
    { key: 'code', header: 'code', width: 140, render: r => <span className="font-mono text-[11.5px] text-stone-700">{r.code}</span> },
    { key: 'name', header: '名称', render: r => <span className="font-medium text-stone-900">{r.name}</span> },
    { key: 'description', header: '说明', render: r => r.description || <span className="text-stone-400">—</span> },
    {
      key: 'is_system',
      header: '类型',
      width: 90,
      render: r => r.is_system ? <Badge variant="primary">内置</Badge> : <Badge variant="outline">自建</Badge>,
    },
    {
      key: 'perms',
      header: '权限数',
      width: 80,
      align: 'right',
      render: r => <span className="tnum font-mono text-[11.5px]">{r.permission_codes.length}</span>,
    },
    {
      key: 'actions',
      header: '操作',
      align: 'right',
      width: 110,
      render: r => (
        <div className="inline-flex items-center gap-0.5">
          <button
            type="button"
            title="权限"
            className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-[11.5px] text-stone-600 hover:bg-stone-200 hover:text-stone-900"
            onClick={() => setPermRole(r)}
          >
            <ShieldCheck className="h-3.5 w-3.5" /> 权限
          </button>
          <button
            type="button"
            title="删除"
            className="rounded p-1 text-stone-600 hover:bg-red-100 hover:text-red-600 disabled:opacity-30 disabled:hover:bg-transparent"
            disabled={r.is_system}
            onClick={() => setDelRole(r)}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <SectionCard>
        <TableToolbar
          title="角色管理"
          extra={
            <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> 新建角色
            </Button>
          }
        />
        <DataTable columns={columns} rows={listQ.data || []} rowKey="id" loading={listQ.isLoading} emptyText="还没有角色" />
      </SectionCard>

      <CreateRoleSheet
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={createMut.mutate}
        loading={createMut.isPending}
      />
      <PermissionsSheet role={permRole} onClose={() => setPermRole(null)} />
      <ConfirmDialog
        open={!!delRole}
        title="删除角色"
        description={`删除 ${delRole?.code} 后，所有关联用户失去该角色权限。`}
        variant="danger"
        confirmText="删除"
        onConfirm={() => delRole && delMut.mutate(delRole.id)}
        onCancel={() => setDelRole(null)}
      />
    </div>
  );
};

const CreateRoleSheet = ({
  open,
  onClose,
  onSubmit,
  loading,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (req: { code: string; name: string; description?: string }) => void;
  loading: boolean;
}) => {
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');

  return (
    <Sheet
      open={open}
      onOpenChange={o => {
        if (!o) {
          setCode('');
          setName('');
          setDesc('');
          onClose();
        }
      }}
    >
      <SheetContent>
        <SheetHeader>
          <SheetTitle>新建角色</SheetTitle>
        </SheetHeader>
        <SheetBody className="space-y-4">
          <div className="space-y-1.5">
            <Label>code（英文唯一标识）</Label>
            <Input value={code} onChange={e => setCode(e.target.value)} placeholder="developer" />
          </div>
          <div className="space-y-1.5">
            <Label>显示名</Label>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="开发者" />
          </div>
          <div className="space-y-1.5">
            <Label>说明</Label>
            <Textarea value={desc} onChange={e => setDesc(e.target.value)} rows={3} />
          </div>
        </SheetBody>
        <SheetFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button
            disabled={loading || !code || !name}
            onClick={() => onSubmit({ code, name, description: desc || undefined })}
          >
            {loading ? '创建中...' : '创建'}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
};

const PermissionsSheet = ({
  role,
  onClose,
}: {
  role: RoleItem | null;
  onClose: () => void;
}) => {
  const qc = useQueryClient();
  const allPermsQ = useQuery({ queryKey: ['permissions'], queryFn: () => permissionApi.list() });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [initd, setInitd] = useState(false);

  // 初始化选中态
  if (role && !initd) {
    setSelected(new Set(role.permission_codes));
    setInitd(true);
  }

  const syncMut = useMutation({
    mutationFn: (codes: string[]) => roleApi.syncPermissions(role!.id, codes),
    onSuccess: () => {
      toast.success('权限已同步');
      qc.invalidateQueries({ queryKey: ['roles'] });
      setInitd(false);
      onClose();
    },
  });

  const handleToggle = (code: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  };

  const grouped: Record<string, { code: string; resource: string; action: string; description: string | null }[]> = {};
  for (const p of allPermsQ.data || []) {
    if (!grouped[p.resource]) grouped[p.resource] = [];
    grouped[p.resource].push(p);
  }

  return (
    <Sheet
      open={!!role}
      onOpenChange={o => {
        if (!o) {
          setInitd(false);
          onClose();
        }
      }}
    >
      <SheetContent width="w-[560px]">
        <SheetHeader>
          <SheetTitle>{role?.name} · 权限分配</SheetTitle>
        </SheetHeader>
        <SheetBody>
          {Object.entries(grouped).map(([resource, perms]) => (
            <div key={resource} className="mb-5">
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-500">
                {resource}
              </div>
              <div className="grid grid-cols-2 gap-2">
                {perms.map(p => (
                  <label
                    key={p.code}
                    className="flex cursor-pointer items-center gap-2 rounded-md border border-stone-200 px-3 py-2 text-sm hover:bg-stone-50"
                  >
                    <input
                      type="checkbox"
                      className="h-3.5 w-3.5"
                      checked={selected.has(p.code)}
                      onChange={() => handleToggle(p.code)}
                    />
                    <span className="font-mono text-xs">{p.code}</span>
                  </label>
                ))}
              </div>
            </div>
          ))}
        </SheetBody>
        <SheetFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button onClick={() => syncMut.mutate(Array.from(selected))} disabled={syncMut.isPending}>
            {syncMut.isPending ? '提交中...' : '同步权限'}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
};
