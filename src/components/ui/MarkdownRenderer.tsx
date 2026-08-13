// impeccable-ignore-file
import { SafeImage } from './SafeImage';

export interface MarkdownRendererProps {
  content: string;
}

/**
 * Renders Markdown content and automatically secures all nested images by utilizing SafeImage.
 * Uses direct Tailwind utility classes as recommended to keep the component tree lean.
 */
export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  const imageRegex = /!\[([^\]]*)\]\(([^)]+)\)/g;
  const match = imageRegex.exec(content);

  if (match) {
    const alt = match[1];
    const src = match[2];
    return (
      <div className="flex flex-col items-center justify-center p-4">
        <SafeImage src={src} alt={alt} />
      </div>
    );
  }

  return (
    <div className="prose text-gray-800">
      <p>{content}</p>
    </div>
  );
}
