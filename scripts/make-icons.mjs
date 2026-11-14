// Generates the extension icons (extension/icons/icon-<size>.png) without dependencies.
// Run: node scripts/make-icons.mjs
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import zlib from 'node:zlib';

export const ICON_SIZES = [16, 32, 48, 96, 128];

const ICONS_DIRECTORY = fileURLToPath(new URL('../extension/icons/', import.meta.url));
const SUPERSAMPLE_GRID = 4;
const SMALL_ICON_MAX_SIZE = 32;
const BACKGROUND_RGB = [0x20, 0x21, 0x24];
const FOREGROUND_RGB = [0xff, 0xff, 0xff];
const CORNER_RADIUS = 0.18;

// Shapes are described in unit coordinates (0..1 of the icon side).
const PLAY_TRIANGLE = [
  [0.36, 0.16],
  [0.36, 0.52],
  [0.68, 0.34],
];
const SUBTITLE_BARS_LEFT = 0.22;
const LONG_BAR_WIDTH = 0.56;
const SHORT_BAR_WIDTH = 0.38;

function subtitleBars(size) {
  // Thicker bars keep the subtitles readable at toolbar sizes.
  const barHeight = size <= SMALL_ICON_MAX_SIZE ? 0.12 : 0.08;
  const firstBarTop = 0.64;
  const gap = size <= SMALL_ICON_MAX_SIZE ? 0.06 : 0.05;
  const secondBarTop = firstBarTop + barHeight + gap;
  return [
    { top: firstBarTop, bottom: firstBarTop + barHeight, width: LONG_BAR_WIDTH },
    { top: secondBarTop, bottom: secondBarTop + barHeight, width: SHORT_BAR_WIDTH },
  ];
}

function isInsideRoundedSquare(x, y) {
  const dx = Math.max(CORNER_RADIUS - x, 0, x - (1 - CORNER_RADIUS));
  const dy = Math.max(CORNER_RADIUS - y, 0, y - (1 - CORNER_RADIUS));
  return dx * dx + dy * dy <= CORNER_RADIUS * CORNER_RADIUS;
}

function isInsideTriangle(x, y, [a, b, c]) {
  const sign = (p, q) => (x - q[0]) * (p[1] - q[1]) - (p[0] - q[0]) * (y - q[1]);
  const d1 = sign(a, b);
  const d2 = sign(b, c);
  const d3 = sign(c, a);
  const hasNegative = d1 < 0 || d2 < 0 || d3 < 0;
  const hasPositive = d1 > 0 || d2 > 0 || d3 > 0;
  return !(hasNegative && hasPositive);
}

function isInsideBar(x, y, bar) {
  return (
    x >= SUBTITLE_BARS_LEFT &&
    x <= SUBTITLE_BARS_LEFT + bar.width &&
    y >= bar.top &&
    y <= bar.bottom
  );
}

/** Renders the icon as RGBA bytes (size * size * 4), anti-aliased by 4x4 supersampling. */
export function renderIcon(size) {
  const bars = subtitleBars(size);
  const rgba = new Uint8Array(size * size * 4);
  const samplesPerPixel = SUPERSAMPLE_GRID * SUPERSAMPLE_GRID;

  for (let pixelY = 0; pixelY < size; pixelY++) {
    for (let pixelX = 0; pixelX < size; pixelX++) {
      let backgroundSamples = 0;
      let foregroundSamples = 0;
      for (let subY = 0; subY < SUPERSAMPLE_GRID; subY++) {
        for (let subX = 0; subX < SUPERSAMPLE_GRID; subX++) {
          const x = (pixelX + (subX + 0.5) / SUPERSAMPLE_GRID) / size;
          const y = (pixelY + (subY + 0.5) / SUPERSAMPLE_GRID) / size;
          if (!isInsideRoundedSquare(x, y)) continue;
          backgroundSamples++;
          if (isInsideTriangle(x, y, PLAY_TRIANGLE) || bars.some((bar) => isInsideBar(x, y, bar))) {
            foregroundSamples++;
          }
        }
      }
      const offset = (pixelY * size + pixelX) * 4;
      if (backgroundSamples === 0) continue;
      const foregroundShare = foregroundSamples / backgroundSamples;
      for (let channel = 0; channel < 3; channel++) {
        rgba[offset + channel] = Math.round(
          BACKGROUND_RGB[channel] * (1 - foregroundShare) + FOREGROUND_RGB[channel] * foregroundShare,
        );
      }
      rgba[offset + 3] = Math.round((backgroundSamples / samplesPerPixel) * 255);
    }
  }
  return rgba;
}

function pngChunk(type, data) {
  const typeAndData = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(zlib.crc32(typeAndData));
  return Buffer.concat([length, typeAndData, checksum]);
}

/** Encodes RGBA bytes as an 8-bit RGBA PNG (filter 0 on every row). */
export function encodePng(size, rgba) {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header[8] = 8; // bit depth
  header[9] = 6; // colour type: RGBA

  const rowBytes = size * 4;
  const filteredRows = Buffer.alloc((rowBytes + 1) * size);
  for (let row = 0; row < size; row++) {
    const rowStart = row * (rowBytes + 1);
    filteredRows[rowStart] = 0;
    Buffer.from(rgba.buffer, rgba.byteOffset + row * rowBytes, rowBytes).copy(filteredRows, rowStart + 1);
  }

  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    pngChunk('IHDR', header),
    pngChunk('IDAT', zlib.deflateSync(filteredRows)),
    pngChunk('IEND', Buffer.alloc(0)),
  ]);
}

function writeIcons() {
  mkdirSync(ICONS_DIRECTORY, { recursive: true });
  for (const size of ICON_SIZES) {
    writeFileSync(join(ICONS_DIRECTORY, `icon-${size}.png`), encodePng(size, renderIcon(size)));
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  writeIcons();
}
