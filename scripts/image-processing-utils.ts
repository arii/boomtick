import { PNG } from 'pngjs';

/**
 * Creates a white PNG canvas of the specified width and height.
 */
export function whiteCanvas(width: number, height: number): PNG {
  const image = new PNG({ width, height });
  for (let index = 0; index < image.data.length; index += 4) {
    image.data[index] = 255;
    image.data[index + 1] = 255;
    image.data[index + 2] = 255;
    image.data[index + 3] = 255;
  }
  return image;
}

/**
 * Copies pixel data from source PNG to target PNG.
 */
export function copyImage(source: PNG, target: PNG): void {
  PNG.bitblt(source, target, 0, 0, source.width, source.height, 0, 0);
}
