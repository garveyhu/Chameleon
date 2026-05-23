/** 添加 workspace 成员 modal —— 走 user_id，admin 给出已有用户列表 */

import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { get } from '@/core/lib/request';
import { Button } from '@/core/components/ui/button';
import { Label } from '@/core/components/ui/label';
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import type { EntityId } from '@/core/types/api';
import type {
  AddMemberPayload,
  MemberRole,
} from '@/system/workspaces/types/workspace';
import { MEMBER_ROLES } from '@/system/workspaces/types/workspace';

interface UserOption {
  id: EntityId;
  username: string;
}

interface Props {
  open: boolean;
  loading: boolean;
  excludeUserIds: Set<string>;
  onClose: () => void;
  onSubmit: (p: AddMemberPayload) => void;
}

export const InviteMemberModal: React.FC<Props> = ({
  open,
  loading,
  excludeUserIds,
  onClose,
  onSubmit,
}) => {
  const [userId, setUserId] = useState('');
  const [role, setRole] = useState<MemberRole>('member');

  const usersQ = useQuery({
    queryKey: ['workspace-modal:users'],
    queryFn: () =>
      get<{ items: UserOption[] }>('/v1/admin/users', {
        params: { page_size: 200 },
      }),
    enabled: open,
    staleTime: 30_000,
  });

  useEffect(() => {
    if (open) {
      setUserId('');
      setRole('member');
    }
  }, [open]);

  const options = (usersQ.data?.items ?? []).filter(
    u => !excludeUserIds.has(String(u.id)),
  );

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="md">
        <ModalHeader>
          <ModalTitle>添加成员</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-3">
          <div className="space-y-1.5">
            <Label>
              用户 <span className="text-rose-500">*</span>
            </Label>
            <Select value={userId} onValueChange={setUserId}>
              <SelectTrigger>
                <SelectValue placeholder="选择用户…" />
              </SelectTrigger>
              <SelectContent>
                {options.map(u => (
                  <SelectItem key={String(u.id)} value={String(u.id)}>
                    {u.username}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>角色</Label>
            <Select value={role} onValueChange={v => setRole(v as MemberRole)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MEMBER_ROLES.map(o => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button
            variant="primary"
            disabled={!userId || loading}
            onClick={() => onSubmit({ user_id: userId, role })}
          >
            {loading ? '添加中…' : '添加'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};
