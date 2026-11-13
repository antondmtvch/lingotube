import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const manifest = JSON.parse(readFileSync(new URL('../manifest.json', import.meta.url), 'utf8'));
const YOUTUBE = ['https://www.youtube.com/*'];

test('manifest is MV3 with minimal permissions', () => {
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual(manifest.permissions, ['storage']);
  assert.equal(manifest.content_scripts.length, 1);
  assert.deepEqual(manifest.content_scripts[0].matches, YOUTUBE);
  assert.deepEqual(manifest.content_scripts[0].js, ['loader.js']);
  assert.deepEqual(manifest.content_scripts[0].css, ['overlay.css']);
  assert.deepEqual(manifest.web_accessible_resources[0].matches, YOUTUBE);
  assert.deepEqual(manifest.web_accessible_resources[0].resources, ['src/*']);
  assert.equal('background' in manifest, false);
  if ('host_permissions' in manifest) assert.deepEqual(manifest.host_permissions, YOUTUBE);
});
