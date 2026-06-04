/** 专业 JSON 编辑器 —— CodeMirror 6：语法高亮 + 实时校验 + 一键格式化 + 错误条。
 *  编辑场景用本组件；只读表格展示仍用 json-cell。 */

import { json } from '@codemirror/lang-json';
import { EditorView } from '@codemirror/view';
import CodeMirror from '@uiw/react-codemirror';
import { useState } from 'react';

import { cn } from '@/core/lib/cn';

interface Props {
  value: string;
  onChange: (v: string) => void;
  readOnly?: boolean;
  minHeight?: string;
  maxHeight?: string;
  className?: string;
  /** 顶部标签，如「输入」「预期输出」 */
  label?: string;
}

const editorTheme = EditorView.theme({
  '&': { fontSize: '12px', backgroundColor: 'transparent' },
  '.cm-content': {
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
  },
  '.cm-gutters': { backgroundColor: 'transparent', border: 'none' },
  '&.cm-focused': { outline: 'none' },
});

export const JsonEditor = ({
  value,
  onChange,
  readOnly,
  minHeight = '110px',
  maxHeight = '320px',
  className,
  label,
}: Props) => {
  const [error, setError] = useState<string | null>(null);

  const handleChange = (v: string) => {
    onChange(v);
    if (!v.trim()) {
      setError(null);
      return;
    }
    try {
      JSON.parse(v);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const format = () => {
    try {
      onChange(JSON.stringify(JSON.parse(value), null, 2));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className={cn('overflow-hidden rounded-md border border-stone-200', className)}>
      <div className="flex items-center justify-between border-b border-stone-100 bg-stone-50/80 px-2 py-1">
        <span className="text-[10.5px] font-medium text-stone-500">
          {label ?? 'JSON'}
        </span>
        {!readOnly && (
          <button
            type="button"
            onClick={format}
            className="text-[10.5px] text-stone-500 transition hover:text-stone-800"
          >
            格式化
          </button>
        )}
      </div>
      <CodeMirror
        value={value}
        onChange={handleChange}
        editable={!readOnly}
        extensions={[json(), editorTheme]}
        minHeight={minHeight}
        maxHeight={maxHeight}
        basicSetup={{
          lineNumbers: true,
          foldGutter: true,
          highlightActiveLine: !readOnly,
          highlightActiveLineGutter: !readOnly,
          autocompletion: false,
        }}
      />
      {error && (
        <div className="border-t border-rose-100 bg-rose-50 px-2 py-1 text-[10.5px] text-rose-600">
          ⚠ JSON 语法错误：{error}
        </div>
      )}
    </div>
  );
};
