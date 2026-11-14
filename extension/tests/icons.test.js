import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { ICON_SIZES, renderIcon } from '../../scripts/make-icons.mjs';

const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const RGBA_COLOR_TYPE = 6;

for (const size of ICON_SIZES) {
  test(`png signature and IHDR size match the file name (icon-${size}.png)`, () => {
    const png = readFileSync(new URL(`../icons/icon-${size}.png`, import.meta.url));
    assert.deepEqual(png.subarray(0, 8), PNG_SIGNATURE);
    assert.equal(png.toString('ascii', 12, 16), 'IHDR');
    assert.equal(png.readUInt32BE(16), size);
    assert.equal(png.readUInt32BE(20), size);
    assert.equal(png[25], RGBA_COLOR_TYPE);
  });
}

test('renderIcon corner pixel is transparent and centre pixel is opaque', () => {
  const size = 128;
  const rgba = renderIcon(size);
  assert.equal(rgba.length, size * size * 4);
  const alphaAt = (x, y) => rgba[(y * size + x) * 4 + 3];
  assert.equal(alphaAt(0, 0), 0);
  assert.equal(alphaAt(64, 64), 255);
});
