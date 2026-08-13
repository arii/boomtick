// impeccable-ignore-file
export interface MarkdownRendererProps {
  content: string;
}

/**
 * Renders Markdown content using standard HTML elements.
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
        <img src={src} alt={alt} className="max-w-full h-auto object-contain" loading="lazy" />
      </div>
    );
  }

  return (
    <div className="prose text-gray-800">
      <p>{content}</p>
    </div>
  );
}
