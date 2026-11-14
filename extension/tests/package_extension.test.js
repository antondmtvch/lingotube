import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { listPackageFiles, assertBundleFresh } from '../../scripts/package-extension.mjs';

const EXTENSION_ROOT = fileURLToPath(new URL('../', import.meta.url));

test('package file list has the manifest, icons, loader and bundle', () => {
  const files = listPackageFiles(EXTENSION_ROOT);
  for (const expected of ['manifest.json', 'loader.js', 'icons/icon-128.png', 'src/page/bundle.js']) {
    assert.ok(files.includes(expected), `missing ${expected}`);
  }
  assert.deepEqual(files, [...files].sort());
});

test('package file list has no tests and no package.json', () => {
  const files = listPackageFiles(EXTENSION_ROOT);
  assert.equal(files.filter((file) => file.startsWith('tests/')).length, 0);
  assert.ok(!files.includes('package.json'));
});

test('assertBundleFresh passes for equal texts and ignores CRLF', () => {
  assert.doesNotThrow(() => assertBundleFresh({ committed: 'a\r\nb\r\n', fresh: 'a\nb\n' }));
});

test('assertBundleFresh throws for a stale bundle', () => {
  assert.throws(() => assertBundleFresh({ committed: 'old', fresh: 'new' }), /build-page-bundle/);
});
