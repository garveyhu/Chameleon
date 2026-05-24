/** 子图编辑 modal —— 在大画布里可视化编辑一个 GraphSpec，应用时落回父字段 */

import { useState } from 'react';

import { Button } from '@/core/components/ui/button';
import {
  Modal,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import { SubgraphCanvas } from '@/system/graphs/components/subgraph-canvas';
import type { GraphSpec } from '@/system/graphs/types/graph';

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  spec: GraphSpec;
  onApply: (spec: GraphSpec) => void;
}

export const SubgraphEditorModal = ({
  open,
  onOpenChange,
  title,
  spec,
  onApply,
}: Props) => {
  const [draft, setDraft] = useState<GraphSpec>(spec);

  return (
    <Modal open={open} onOpenChange={onOpenChange}>
      <ModalContent
        size="xl"
        className="h-[88vh] w-[min(1180px,94vw)]"
        closeOnBackdrop={false}
      >
        <ModalHeader>
          <ModalTitle>{title}</ModalTitle>
        </ModalHeader>
        <div className="min-h-0 flex-1">
          <SubgraphCanvas spec={spec} onChange={setDraft} />
        </div>
        <ModalFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            onClick={() => {
              onApply(draft);
              onOpenChange(false);
            }}
          >
            应用
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};
