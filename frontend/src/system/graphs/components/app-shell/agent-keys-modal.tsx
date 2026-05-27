/** 智能体密钥管理弹窗 —— 在编辑器内为「当前智能体」生成 / 删除专属 API Key
 *
 * 作用域：scope_type='app'、scope_ref=agent_key，仅对该 agent 的 invoke / chat completions 有效。
 * 复用 AppKeysPanel 展示与交互（应用详情页「API」tab 同款），此处按 graph_id 注入端点。
 */
import { KeyRound } from 'lucide-react';

import {
  Modal,
  ModalBody,
  ModalContent,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import type { EntityId } from '@/core/types/api';
import { AppKeysPanel } from '@/system/agents/components/app-keys-panel';
import { graphApi } from '@/system/graphs/services/graph';

interface Props {
  graphId: EntityId;
  open: boolean;
  onClose: () => void;
}

export const AgentKeysModal = ({ graphId, open, onClose }: Props) => (
  <Modal open={open} onOpenChange={o => !o && onClose()}>
    <ModalContent size="lg">
      <ModalHeader>
        <ModalTitle className="flex items-center gap-2">
          <KeyRound className="h-4 w-4 text-stone-500" />
          智能体密钥
        </ModalTitle>
      </ModalHeader>
      <ModalBody>
        {open && (
          <AppKeysPanel
            queryKey={['agent-keys', graphId]}
            keysApi={{
              list: () => graphApi.listAgentKeys(graphId),
              create: name => graphApi.createAgentKey(graphId, name),
              revoke: keyId => graphApi.revokeAgentKey(graphId, keyId),
            }}
          />
        )}
      </ModalBody>
    </ModalContent>
  </Modal>
);
