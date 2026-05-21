/** 系统配置 + 导入导出 */

import { useMutation } from '@tanstack/react-query';
import { Download, Upload } from 'lucide-react';
import { useRef, useState } from 'react';
import { toast } from 'sonner';

import { SectionCard } from '@/core/components/table';
import { Button } from '@/core/components/ui/button';
import { getRaw, postForm } from '@/core/lib/request';

export const SettingsPage = () => {
  const [importing, setImporting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const exportMut = useMutation({
    mutationFn: async () => {
      const { data, headers } = await getRaw<Blob>('/v1/admin/settings/export-json');
      const cd = headers['content-disposition'] || '';
      const m = cd.match(/filename="?([^"]+)"?/);
      const filename = m?.[1] || `chameleon-backup-${Date.now()}.zip`;
      const url = URL.createObjectURL(data);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      return filename;
    },
    onSuccess: f => toast.success(`已下载 ${f}`),
  });

  const handleImport = async (file: File) => {
    if (!confirm(`确定导入 ${file.name}？现有数据将被 UPSERT 合并。`)) return;
    setImporting(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('confirm', 'true');
      const result = await postForm<{
        apps_upserted: number;
        users_upserted: number;
        providers_upserted: number;
        models_upserted: number;
        agents_upserted: number;
        embed_configs_upserted: number;
        api_keys_upserted: number;
        warnings: string[];
      }>('/v1/admin/settings/import-json', fd);
      toast.success(
        `导入完成：apps ${result.apps_upserted} / users ${result.users_upserted} / providers ${result.providers_upserted} / models ${result.models_upserted} / agents ${result.agents_upserted}`,
      );
      if (result.warnings.length > 0) {
        toast.warning(`${result.warnings.length} 条警告，详见浏览器 console`);
        console.warn('Import warnings:', result.warnings);
      }
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  return (
    <div>
      <SectionCard>
        <h3 className="mb-1 text-[13.5px] font-semibold text-stone-900">系统配置 · 配置备份</h3>
        <p className="mb-4 text-[12px] text-stone-500">
          导出 zip 含：apps / users / providers / models / agents / embed_configs。
          providers.api_key 仍是加密文 —— 异机还原需要相同的 CHAMELEON_CRYPTO_KEY。
        </p>
        <div className="flex gap-2">
          <Button variant="primary" size="sm" onClick={() => exportMut.mutate()} disabled={exportMut.isPending}>
            <Download className="h-3.5 w-3.5" />
            {exportMut.isPending ? '导出中...' : '导出全部配置'}
          </Button>
          <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()} disabled={importing}>
            <Upload className="h-3.5 w-3.5" />
            {importing ? '导入中...' : '导入 zip'}
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept=".zip"
            className="hidden"
            onChange={e => {
              const file = e.target.files?.[0];
              if (file) handleImport(file);
            }}
          />
        </div>
      </SectionCard>
    </div>
  );
};
