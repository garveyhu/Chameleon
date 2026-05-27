/** 知识库「服务 API」弹窗 —— 对标 Dify：API 端点 + 密钥（kbs-）+ 文档入口
 *
 * 密钥为 KB 作用域（kbs- 前缀），仅对该 KB 的公开 API /v1/kbs/{kb_key}/* 有效，
 * 与应用密钥（通吃）、智能体密钥（agent-）区分。密钥表抽到 KbKeysManager 复用。
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { BookOpen, Check, Copy, KeyRound } from 'lucide-react';

import {
  Modal,
  ModalBody,
  ModalContent,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import { toast } from '@/core/lib/toast';
import { KbKeysManager } from '@/system/kbs/components/kb-keys-manager';
import type { KbItem } from '@/system/kbs/types/kb';

interface Props {
  kb: KbItem;
  open: boolean;
  onClose: () => void;
}

export const KbServiceApiModal = ({ kb, open, onClose }: Props) => {
  const navigate = useNavigate();
  const endpoint = `${window.location.origin}/v1/kbs/${kb.kb_key}`;

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="lg">
        <ModalHeader>
          <ModalTitle className="flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-stone-500" />
            服务 API
          </ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          {/* API 端点 */}
          <div>
            <div className="mb-1 flex items-center justify-between">
              <label className="text-[12px] text-stone-600">API 端点</label>
              <button
                type="button"
                onClick={() => navigate(`/api-docs/kb/${kb.kb_key}`)}
                className="inline-flex items-center gap-1 text-[11.5px] text-blue-600 hover:text-blue-700"
              >
                <BookOpen className="h-3.5 w-3.5" />
                查看 API 文档
              </button>
            </div>
            <CopyRow value={endpoint} />
            <p className="mt-1 text-[10.5px] text-stone-400">
              在此基址下调用检索 / 文档增改删查；请求头带 Authorization: Bearer 你的密钥。
            </p>
          </div>

          {/* 密钥管理 */}
          <KbKeysManager kbId={kb.id} />
        </ModalBody>
      </ModalContent>
    </Modal>
  );
};

const CopyRow = ({ value }: { value: string }) => {
  const [copied, setCopied] = useState(false);
  const copy = () =>
    void navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      toast.success('已复制');
      setTimeout(() => setCopied(false), 1500);
    });
  return (
    <div className="flex items-center gap-2 rounded-md border border-stone-200 bg-stone-50/60 px-2.5 py-1.5">
      <code className="flex-1 truncate font-mono text-[11.5px] text-stone-700">{value}</code>
      <button type="button" onClick={copy} className="shrink-0 text-stone-400 hover:text-stone-700">
        {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
    </div>
  );
};
