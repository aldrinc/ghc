import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeExternalLinks from "rehype-external-links";
import { cn } from "@/lib/utils";

type MarkdownViewerProps = {
  content: string;
  className?: string;
};

export function MarkdownViewer({ content, className }: MarkdownViewerProps) {
  return (
    <article className={cn("mx-auto w-full max-w-[75ch] px-4 sm:px-6", "markdown", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[
          [
            rehypeExternalLinks,
            {
              target: "_blank",
              rel: ["noopener", "noreferrer"],
            },
          ],
        ]}
        components={{
          table({ children, className: tableClassName, node: _node, ...props }) {
            return (
              <div className="my-6 w-full overflow-x-auto rounded-xl border border-border">
                <table {...props} className={cn("w-full", tableClassName)}>
                  {children}
                </table>
              </div>
            );
          },
          code({ inline, children, className: codeClassName, node: _node, ...props }) {
            const text = String(children ?? "").trim();
            const looksLikeUrl = inline && /^https?:\/\/\S+$/i.test(text);

            if (looksLikeUrl) {
              return (
                <a
                  href={text}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center rounded-md border border-border bg-surface-2 px-2 py-0.5 font-mono text-[0.95em] text-primary no-underline hover:opacity-80"
                >
                  {text}
                </a>
              );
            }

            return (
              <code className={codeClassName} {...props}>
                {children}
              </code>
            );
          },
        }}
      >
        {content?.trim() ? content : "_No content available._"}
      </ReactMarkdown>
    </article>
  );
}
