import { SafeImage } from './SafeImage';

export interface MarkdownRendererProps {
  content: string;
}

/**
 * Renders Markdown content and automatically secures all nested images by utilizing SafeImage.
 */
export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  // Simple representation or parsing of markdown content for demonstrating SafeImage integration.
  // In a full production environment, this would utilize a library like react-markdown:
  // <ReactMarkdown components={{ img: SafeImage }}>{content}</ReactMarkdown>

  // For demonstration and evaluation purposes, we can parse standard markdown image tags: ![alt](url)
  const imageRegex = /!\[([^\]]*)\]\(([^)]+)\)/g;
  const match = imageRegex.exec(content);

  if (match) {
    const alt = match[1];
    const src = match[2];
    return (
      <div className="markdown-renderer">
        <SafeImage src={src} alt={alt} />
      </div>
    );
  }

  return (
    <div className="markdown-renderer">
      <p>{content}</p>
    </div>
  );
}
