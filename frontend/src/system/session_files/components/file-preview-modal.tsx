/** 文件预览弹窗 —— 居中模态，按类型渲染（图片 / PDF / 音频 / 文本 / Office 抽取文本）。
 *
 * Markdown 默认渲染成富文本，可切「原文」看源码；其余文本走等宽 pre。
 * 列表行眼睛 icon 与详情抽屉「预览」行共用此组件。
 */

import { useQuery } from '@tanstack/react-query';
import { Braces, Download, FileText, Loader2 } from 'lucide-react';
import { useState } from 'react';

import { Markdown } from '@/core/components/chat/markdown';
import { Button } from '@/core/components/ui/button';
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import { cn } from '@/core/lib/cn';
import { sessionFileApi } from '@/system/session_files/services/session-file';
import type { SessionFilePreview } from '@/system/session_files/types/session-file';

export interface PreviewTarget {
  id: number;
  filename: string;
  mime?: string;
}

const isMarkdown = (t: PreviewTarget): boolean =>
  /\.(md|markdown)$/i.test(t.filename) || (t.mime ?? '').includes('markdown');

export const FilePreviewModal = ({
  file,
  onClose,
}: {
  file: PreviewTarget | null;
  onClose: () => void;
}) => {
  const open = !!file;
  const q = useQuery({
    queryKey: ['session-files', 'preview', file?.id],
    queryFn: () => sessionFileApi.preview(file!.id),
    enabled: open,
  });

  return (
    <Modal open={open} onOpenChange={o => !o && onClose()}>
      <ModalContent size="lg" className="flex h-[82vh] flex-col">
        <ModalHeader>
          <ModalTitle className="truncate pr-6">{file?.filename ?? '文件预览'}</ModalTitle>
        </ModalHeader>
        <ModalBody className="flex min-h-0 flex-1 flex-col !p-0">
          {/* 按 file.id remount：切文件时「渲染/原文」切换态重置，避开 effect */}
          {file ? (
            <PreviewPane
              key={file.id}
              file={file}
              loading={q.isLoading}
              preview={q.data ?? null}
            />
          ) : null}
        </ModalBody>
      </ModalContent>
    </Modal>
  );
};

const PreviewPane = ({
  file,
  loading,
  preview,
}: {
  file: PreviewTarget;
  loading: boolean;
  preview: SessionFilePreview | null;
}) => {
  const md = isMarkdown(file);
  const [raw, setRaw] = useState(false);
  const hasText = (preview?.kind === 'text' || preview?.kind === 'office') && preview.text != null;

  return (
    <div className="flex h-full flex-col">
      {/* 工具条：md 渲染/原文切换 + 下载 */}
      <div className="flex h-9 shrink-0 items-center justify-between border-b border-stone-200 px-4">
        <div className="flex items-center gap-0.5">
          {md && hasText ? (
            <>
              <button
                type="button"
                title="渲染"
                onClick={() => setRaw(false)}
                className={cn(
                  'rounded p-1 transition',
                  !raw ? 'bg-stone-100 text-stone-700' : 'text-stone-300 hover:text-stone-500',
                )}
              >
                <FileText className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                title="原文"
                onClick={() => setRaw(true)}
                className={cn(
                  'rounded p-1 transition',
                  raw ? 'bg-stone-100 text-stone-700' : 'text-stone-300 hover:text-stone-500',
                )}
              >
                <Braces className="h-3.5 w-3.5" />
              </button>
            </>
          ) : (
            <span className="text-[11px] text-stone-400">
              {preview?.truncated ? '预览已截断' : ''}
            </span>
          )}
        </div>
        {preview?.url ? (
          <Button asChild variant="outline" size="sm">
            <a href={preview.url} download={file.filename}>
              <Download className="mr-1 h-3.5 w-3.5" />
              下载源文件
            </a>
          </Button>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        <PreviewContent file={file} loading={loading} preview={preview} md={md} raw={raw} />
      </div>
    </div>
  );
};

const PreviewContent = ({
  file,
  loading,
  preview,
  md,
  raw,
}: {
  file: PreviewTarget;
  loading: boolean;
  preview: SessionFilePreview | null;
  md: boolean;
  raw: boolean;
}) => {
  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-[12px] text-stone-400">
        <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> 加载预览中…
      </div>
    );
  }
  if (!preview) {
    return <Centered>无预览数据</Centered>;
  }
  if (preview.note) {
    return (
      <div className="m-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-4 text-[12px] text-amber-700">
        {preview.note}
      </div>
    );
  }
  if (preview.kind === 'image' && preview.url) {
    return (
      <div className="flex h-full items-center justify-center bg-stone-50 p-4">
        <img src={preview.url} alt={file.filename} className="max-h-full max-w-full object-contain" />
      </div>
    );
  }
  if (preview.kind === 'pdf' && preview.url) {
    return <iframe title={file.filename} src={preview.url} className="h-full w-full" />;
  }
  if (preview.kind === 'audio' && preview.url) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <audio controls src={preview.url} className="w-full max-w-md" />
      </div>
    );
  }
  if ((preview.kind === 'text' || preview.kind === 'office') && preview.text != null) {
    if (md && !raw) {
      return (
        <div className="px-5 py-4 text-[13px] leading-relaxed text-stone-800">
          <Markdown content={preview.text} />
        </div>
      );
    }
    return (
      <pre className="whitespace-pre-wrap break-words px-5 py-4 font-mono text-[12px] leading-relaxed text-stone-800">
        {preview.text}
      </pre>
    );
  }
  return <Centered>该类型不支持内嵌预览，请用上方按钮下载查看</Centered>;
};

const Centered = ({ children }: { children: React.ReactNode }) => (
  <div className="flex h-full items-center justify-center px-6 text-center text-[12px] text-stone-400">
    {children}
  </div>
);
