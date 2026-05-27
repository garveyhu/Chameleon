/** 知识库密钥管理弹窗（纯密钥）—— API 文档页「管理密钥」用
 *
 * 与「服务 API 弹窗」区分：那个还带端点 + 文档入口；文档页里已在文档上下文，
 * 故只露密钥管理（对标智能体文档页的 AgentKeysModal）。密钥表复用 KbKeysManager。
 */
import { KeyRound, ShieldCheck } from 'lucide-react';

import {
  Modal,
  ModalBody,
  ModalContent,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import type { EntityId } from '@/core/types/api';
import { KbKeysManager } from '@/system/kbs/components/kb-keys-manager';

interface Props {
  kbId: EntityId;
  open: boolean;
  onClose: () => void;
}

export const KbKeysModal = ({ kbId, open, onClose }: Props) => (
  <Modal open={open} onOpenChange={o => !o && onClose()}>
    <ModalContent size="lg">
      <ModalHeader>
        <ModalTitle className="flex items-center gap-2">
          <KeyRound className="h-4 w-4 text-stone-500" />
          知识库密钥
        </ModalTitle>
      </ModalHeader>
      <ModalBody className="space-y-4">
        <div className="flex items-start gap-2 rounded-lg border border-sky-100 bg-sky-50/60 px-3 py-2 text-[11.5px] leading-relaxed text-sky-800">
          <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-sky-500" />
          <span>
            此处生成的密钥<strong>仅对本知识库有效</strong>（调用其检索 / 文档接口）；与「应用密钥」不同，应用密钥默认对所有系统端点有效。
          </span>
        </div>
        <KbKeysManager kbId={kbId} />
      </ModalBody>
    </ModalContent>
  </Modal>
);
