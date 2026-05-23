/** 多模态附件按钮 —— 文件选择 + 上传进度 + 缩略图预览
 *
 * 复用 file-upload helper：三步走（presign → PUT → finalize）；
 * 上传完后回调 onAttached(UploadResult) → 调用方串到当前 input 的 attachments 列表。
 */

import { Loader2, Paperclip, X } from 'lucide-react';
import { useId, useRef, useState } from 'react';

import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import {
  uploadFile,
  type UploadResult,
} from '@/system/files/services/file-upload';

const _MAX_BYTES = 20 * 1024 * 1024;

interface Props {
  /** 已附件列表（受控）—— 父级渲染 + 移除 */
  attachments: UploadResult[];
  /** 上传完成后追加一个 attachment */
  onAttached: (a: UploadResult) => void;
  /** 移除 */
  onRemove: (object_id: string) => void;
  disabled?: boolean;
}

export const FileAttachButton: React.FC<Props> = ({
  attachments,
  onAttached,
  onRemove,
  disabled,
}) => {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = '';
    if (!files.length) return;

    setUploading(true);
    try {
      for (const f of files) {
        if (f.size <= 0 || f.size > _MAX_BYTES) {
          toast.error(`${f.name}: 文件大小非法 (limit 20MB)`);
          continue;
        }
        try {
          const r = await uploadFile(f);
          onAttached(r);
        } catch (err) {
          toast.error(
            `${f.name} 上传失败: ${(err as Error).message ?? '未知错误'}`,
          );
        }
      }
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept="image/*,audio/*,application/pdf"
        multiple
        className="hidden"
        onChange={handleChange}
        disabled={disabled || uploading}
      />
      <button
        type="button"
        title="上传附件（图片 / 音频 / PDF，最大 20MB）"
        onClick={() => inputRef.current?.click()}
        disabled={disabled || uploading}
        className={cn(
          'inline-flex h-7 w-7 items-center justify-center rounded-md border border-stone-200/70 bg-white text-stone-500 transition',
          'hover:border-amber-300 hover:bg-amber-50/40 hover:text-amber-700',
          'disabled:cursor-not-allowed disabled:opacity-50',
        )}
      >
        {uploading ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Paperclip className="h-3.5 w-3.5" />
        )}
      </button>

      {attachments.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {attachments.map(a => (
            <AttachmentChip
              key={a.object_id}
              attachment={a}
              onRemove={() => onRemove(a.object_id)}
            />
          ))}
        </div>
      )}
    </div>
  );
};

interface ChipProps {
  attachment: UploadResult;
  onRemove: () => void;
}

const AttachmentChip: React.FC<ChipProps> = ({ attachment, onRemove }) => {
  const isImage = attachment.mime_kind === 'image';
  return (
    <div
      className={cn(
        'group relative flex items-center gap-1 rounded-md border border-stone-200/70 bg-stone-50/60 px-1.5 py-0.5 text-[11px]',
      )}
      title={`${attachment.content_type ?? attachment.mime_kind} · ${formatSize(attachment.size)}`}
    >
      {isImage ? (
        <img
          src={attachment.object_url}
          alt=""
          className="h-5 w-5 rounded object-cover"
        />
      ) : (
        <span className="text-stone-500">{attachment.mime_kind}</span>
      )}
      <span className="max-w-[80px] truncate text-stone-700">
        {attachment.object_id.split('/').pop()}
      </span>
      <button
        type="button"
        onClick={onRemove}
        className="rounded p-0.5 text-stone-400 hover:bg-rose-100 hover:text-rose-600"
        title="移除"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
};

function formatSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}
