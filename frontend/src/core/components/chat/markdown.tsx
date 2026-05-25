/** 聊天消息 Markdown 渲染 —— react-markdown + gfm，元素映射成轻量 Tailwind 样式
 *
 * 给 assistant 消息用（列表 / 加粗 / 代码 / 表格 / 链接）。只取 children/href，
 * 不透传 node，避免无效 DOM 属性告警。
 */
import ReactMarkdown from 'react-markdown';

import remarkGfm from 'remark-gfm';

import { cn } from '@/core/lib/cn';

interface Props {
  content: string;
  className?: string;
}

export const Markdown = ({ content, className }: Props) => (
  <div className={cn('text-[13.5px] leading-relaxed break-words', className)}>
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
        ul: ({ children }) => (
          <ul className="mb-2 list-disc space-y-0.5 pl-5 last:mb-0">{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="mb-2 list-decimal space-y-0.5 pl-5 last:mb-0">{children}</ol>
        ),
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
        a: ({ children, href }) => (
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="text-sky-600 underline underline-offset-2"
          >
            {children}
          </a>
        ),
        strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
        em: ({ children }) => <em className="italic">{children}</em>,
        h1: ({ children }) => <h1 className="mt-1 mb-1.5 text-[15px] font-semibold">{children}</h1>,
        h2: ({ children }) => <h2 className="mt-1 mb-1.5 text-[14px] font-semibold">{children}</h2>,
        h3: ({ children }) => <h3 className="mt-1 mb-1 text-[13px] font-semibold">{children}</h3>,
        blockquote: ({ children }) => (
          <blockquote className="mb-2 border-l-2 border-stone-300 pl-2 text-stone-500">
            {children}
          </blockquote>
        ),
        code: ({ children }) => (
          <code className="rounded bg-stone-100 px-1 py-0.5 font-mono text-[0.85em] text-stone-800">
            {children}
          </code>
        ),
        pre: ({ children }) => (
          <pre className="mb-2 overflow-x-auto rounded-md bg-stone-100 p-2.5 font-mono text-[12px] last:mb-0 [&>code]:bg-transparent [&>code]:p-0 [&>code]:text-stone-800">
            {children}
          </pre>
        ),
        table: ({ children }) => (
          <div className="mb-2 overflow-x-auto">
            <table className="w-full border-collapse text-[12px]">{children}</table>
          </div>
        ),
        th: ({ children }) => (
          <th className="border border-stone-200 px-2 py-1 text-left font-medium">{children}</th>
        ),
        td: ({ children }) => <td className="border border-stone-200 px-2 py-1">{children}</td>,
        hr: () => <hr className="my-2 border-stone-200" />,
      }}
    >
      {content}
    </ReactMarkdown>
  </div>
);
