import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const manifest = JSON.parse(readFileSync(new URL('../manifest.json', import.meta.url), 'utf8'));
const YOUTUBE = ['https://www.youtube.com/*'];

test('manifest is MV3 with minimal permissions', () => {
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual(manifest.permissions, ['storage']);
  assert.equal(manifest.content_scripts.length, 2);
  assert.deepEqual(manifest.content_scripts[0].matches, YOUTUBE);
  assert.deepEqual(manifest.content_scripts[0].js, ['loader.js']);
  assert.deepEqual(manifest.content_scripts[0].css, ['overlay.css']);
  assert.notEqual(manifest.content_scripts[0].world, 'MAIN');
  assert.deepEqual(manifest.content_scripts[1].js, ['src/page/bundle.js']);
  assert.equal(manifest.content_scripts[1].world, 'MAIN');
  assert.equal('web_accessible_resources' in manifest, false);
  assert.equal('background' in manifest, false);
  if ('host_permissions' in manifest) assert.deepEqual(manifest.host_permissions, YOUTUBE);
});

test('manifest declares icons of every size and the files exist', () => {
  assert.deepEqual(Object.keys(manifest.icons), ['16', '32', '48', '96', '128']);
  for (const size of Object.keys(manifest.icons)) {
    assert.equal(manifest.icons[size], `icons/icon-${size}.png`);
    assert.ok(readFileSync(new URL(`../${manifest.icons[size]}`, import.meta.url)).length > 0);
  }
});

test('manifest description is a non-empty English string', () => {
  assert.equal(typeof manifest.description, 'string');
  assert.ok(manifest.description.length > 0);
  assert.doesNotMatch(manifest.description, /[А-Яа-яЁё]/);
});

test('manifest version is X.Y.Z', () => {
  assert.match(manifest.version, /^\d+\.\d+\.\d+$/);
});

test('manifest sets browser minimums', () => {
  assert.equal(manifest.minimum_chrome_version, '111');
  assert.equal(manifest.browser_specific_settings.gecko.strict_min_version, '140.0');
});

test('manifest sets the Firefox for Android minimum to 142', () => {
  assert.equal(manifest.browser_specific_settings.gecko_android.strict_min_version, '142.0');
});

test('manifest declares no data collection', () => {
  assert.deepEqual(manifest.browser_specific_settings.gecko.data_collection_permissions, {
    required: ['none'],
  });
});

test('gecko id is unchanged', () => {
  assert.equal(
    manifest.browser_specific_settings.gecko.id,
    '{8f3c2a1e-5b7d-4e9a-9c61-2d0f4b8e7a35}',
  );
});
