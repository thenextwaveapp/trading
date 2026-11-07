import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import s from "./Markdown.module.css";

/** Renders the assistant's markdown as real elements — bold, lists, inline code,
 *  links — instead of showing the raw `**` and `1.` characters. react-markdown
 *  builds React nodes (no dangerouslySetInnerHTML, nothing to sanitize), and
 *  re-parsing the whole string on each streamed token is cheap for short chat
 *  replies. Links are forced to open safely in a new tab. */
export default function Markdown({ children }: { children: string }) {
  return (
    <div className={s.md}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node: _node, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
