import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface MarkdownViewProps {
  value: string
}

export function MarkdownView({ value }: MarkdownViewProps) {
  return (
    <div className="markdown-view">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{value}</ReactMarkdown>
    </div>
  )
}

export default MarkdownView
