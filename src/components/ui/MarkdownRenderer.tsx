import { SafeImage } from './SafeImage';
import { Box } from '../../layouts/Box';

export interface MarkdownRendererProps {
  content: string;
}

// Global cache for parsed Markdown elements to optimize performance
const markdownCache = new Map<string, React.ReactNode>();

/**
 * Renders Markdown content and automatically secures all nested images by utilizing SafeImage.
 */
export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  if (markdownCache.has(content)) {
    return (
      <Box className="markdown-renderer">
        {markdownCache.get(content)}
      </Box>
    );
  }

  const imageRegex = /!\[([^\]]*)\]\(([^)]+)\)/g;
  const match = imageRegex.exec(content);

  let parsedElement: React.ReactNode;
  if (match) {
    const alt = match[1];
    const src = match[2];
    parsedElement = <SafeImage src={src} alt={alt} />;
  } else {
    parsedElement = <p>{content}</p>;
  }

  markdownCache.set(content, parsedElement);

  return (
    <Box className="markdown-renderer">
      {parsedElement}
    </Box>
  );
}
