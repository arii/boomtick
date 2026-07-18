import { describe, it, expect } from 'vitest';
import { isSafeUrl, SafeImage } from '../../src/components/ui/SafeImage';
import { MarkdownRenderer } from '../../src/components/ui/MarkdownRenderer';

// Helper to get the underlying function of a React component (handles memo/forwardRef wrapper objects)
function getComponentFunction(component: any): any {
  if (typeof component === 'function') return component;
  if (component && typeof component === 'object' && component.type) {
    return component.type;
  }
  return component;
}

describe('isSafeUrl', () => {
  it('allows http, https, and relative paths', () => {
    expect(isSafeUrl('http://example.com/image.png')).toBe(true);
    expect(isSafeUrl('https://example.com/image.png')).toBe(true);
    expect(isSafeUrl('/images/hero.jpg')).toBe(true);
  });

  it('rejects data, javascript, and other unsafe protocols', () => {
    expect(isSafeUrl('javascript:alert(1)')).toBe(false);
    expect(isSafeUrl('data:image/png;base64,iVBORw0K')).toBe(false);
    expect(isSafeUrl('ftp://example.com/file')).toBe(false);
    expect(isSafeUrl('')).toBe(false);
    expect(isSafeUrl(undefined)).toBe(false);
  });
});

describe('SafeImage', () => {
  const renderSafeImage = getComponentFunction(SafeImage);

  it('returns null if the URL is unsafe', () => {
    const element = renderSafeImage({ src: 'javascript:alert(1)' });
    expect(element).toBeNull();
  });

  it('renders standard img tag properties correctly', () => {
    const element = renderSafeImage({
      src: 'https://example.com/photo.png',
      alt: 'Scenic view',
      title: 'Nice photography',
    });

    expect(element).toBeDefined();
    expect(element?.type).toBe('img');
    expect(element?.props.src).toBe('https://example.com/photo.png');
    expect(element?.props.alt).toBe('Scenic view');
    expect(element?.props.title).toBe('Nice photography');
    expect(element?.props.loading).toBe('lazy');
  });

  it('applies the external asset policy for non-local assets', () => {
    const element = renderSafeImage({ src: 'https://external-domain.com/pic.jpg' });
    expect(element?.props.crossOrigin).toBe('anonymous');
    expect(element?.props.referrerPolicy).toBe('no-referrer');
  });

  it('does not apply external asset policy for local assets', () => {
    const element = renderSafeImage({ src: '/local/pic.jpg' });
    expect(element?.props.crossOrigin).toBeUndefined();
    expect(element?.props.referrerPolicy).toBeUndefined();
  });

  it('enforces objectFit contain and default style parameters', () => {
    const element = renderSafeImage({
      src: 'https://example.com/hero.jpg',
      maxHeight: '50vh',
    });

    expect(element?.props.style).toEqual({
      objectFit: 'contain',
      maxHeight: '50vh',
    });
  });
});

describe('MarkdownRenderer', () => {
  const renderMarkdownRenderer = getComponentFunction(MarkdownRenderer);

  it('renders normal text safely', () => {
    const element = renderMarkdownRenderer({ content: 'Just some regular text.' });
    expect(element).toBeDefined();
    expect(element.props.className).toBe('markdown-renderer');
  });

  it('correctly parses and uses SafeImage for markdown images', () => {
    const element = renderMarkdownRenderer({ content: '![Awesome Image](https://example.com/img.png)' });
    expect(element).toBeDefined();
    expect(element.props.className).toBe('markdown-renderer');

    const children = element.props.children;
    expect(children).toBeDefined();
    expect(children.type).toBe(SafeImage);
    expect(children.props.src).toBe('https://example.com/img.png');
    expect(children.props.alt).toBe('Awesome Image');
  });
});
