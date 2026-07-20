import { ImgHTMLAttributes, memo } from 'react';
import { SPACING_MAP, SpacingToken } from '../../layouts/layout-maps';

// Protocol Whitelist: Allow only http:, https:, or / (relative) paths
export function isSafeUrl(url?: string): boolean {
  if (!url) return false;
  if (url.startsWith('/')) return true;
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

export interface SafeImageProps extends Omit<ImgHTMLAttributes<HTMLImageElement>, 'maxHeight'> {
  maxHeight?: SpacingToken | string | number;
  objectFit?: 'contain' | 'cover' | 'fill' | 'none' | 'scale-down';
}

/**
 * Reusable security-hardened Image component.
 * Ensures image rendering conforms to strict protocol/prop whitelists and asset safety.
 */
export const SafeImage = memo(function SafeImage({
  src,
  alt = '',
  loading = 'lazy',
  title,
  srcSet,
  className,
  style,
  width,
  height,
  maxHeight,
  objectFit = 'contain',
}: SafeImageProps) {
  // Protocol whitelist filter
  const safeSrc = isSafeUrl(src) ? src : undefined;

  // External asset policy
  const isExternal = src && (src.startsWith('http://') || src.startsWith('https://'));
  const crossOrigin = isExternal ? 'anonymous' : undefined;
  const referrerPolicy = isExternal ? 'no-referrer' : undefined;

  // Resolve maxHeight design token if passed
  const resolvedMaxHeight = maxHeight && maxHeight in SPACING_MAP
    ? SPACING_MAP[maxHeight as SpacingToken]
    : maxHeight;

  // Enforce editorial constraints: object-contain by default, specific maxHeight handling if passed
  const combinedStyle = {
    objectFit,
    maxHeight: resolvedMaxHeight || undefined,
    ...style,
  };

  if (!safeSrc) {
    return null;
  }

  return (
    <img
      src={safeSrc}
      alt={alt}
      loading={loading}
      title={title}
      srcSet={srcSet}
      className={className}
      style={combinedStyle}
      width={width}
      height={height}
      crossOrigin={crossOrigin}
      referrerPolicy={referrerPolicy}
    />
  );
});
SafeImage.displayName = 'SafeImage';
