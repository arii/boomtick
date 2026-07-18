import { SafeImage } from './SafeImage';
import { Box } from '../../layouts/Box';

export interface MarkdownRendererProps {
  content: string;
}

// Global cache for parsed Markdown elements to optimize performance
const markdownCache = new Map<string, React.ReactNode>();
const MAX_CACHE_SIZE = 100;

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

  // Evict oldest entry (FIFO) if cache size exceeds the limit to prevent memory leak
  if (markdownCache.size >= MAX_CACHE_SIZE) {
    const firstKey = markdownCache.keys().next().value;
    if (firstKey !== undefined) {
      markdownCache.delete(firstKey);
    }
  }

  markdownCache.set(content, parsedElement);

  return (
    <Box className="markdown-renderer">
      {parsedElement}
    </Box>
  );
}
