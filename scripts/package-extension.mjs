// Builds the release archives of the browser extension.
//
// Usage (from the repo root):
//   node scripts/package-extension.mjs chromium   -> dist/lingotube-<version>-chromium.zip
//   node scripts/package-extension.mjs source     -> dist/lingotube-<version>-source.zip
//
// `chromium` first checks that the committed page bundle matches its sources, then builds the
// zip with web-ext (run through npx). `source` archives the committed tree (git archive HEAD),
// which is the human-readable source code that Mozilla asks for.

import { mkdirSync, readFileSync, readdirSync } from 'node:fs';
import { join, relative, resolve, sep } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { buildPageBundle } from './build-page-bundle.mjs';

const REPO_ROOT = fileURLToPath(new URL('../', import.meta.url));
const EXTENSION_ROOT = join(REPO_ROOT, 'extension');
const ARTIFACTS_DIR = join(REPO_ROOT, 'dist');
const COMMITTED_BUNDLE_FILE = join(EXTENSION_ROOT, 'src/page/bundle.js');
const WEB_EXT = 'web-ext@10.8.0';
export const PACKAGE_IGNORE_GLOBS = ['tests', 'tests/**', 'package.json'];

const quoteForShell = (text) => `"${text}"`;
const normalizeLineEndings = (text) => text.replace(/\r\n/g, '\n');

/** Paths (relative to the extension root, with '/') that go into the package, sorted. */
export function listPackageFiles(extensionRoot) {
  const files = readdirSync(extensionRoot, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => relative(extensionRoot, join(entry.parentPath, entry.name)).split(sep).join('/'))
    .filter((file) => !file.startsWith('tests/') && file !== 'package.json');
  return files.sort();
}

/** Throws when the committed page bundle differs from a fresh build of its sources. */
export function assertBundleFresh({
  committed = readFileSync(COMMITTED_BUNDLE_FILE, 'utf8'),
  fresh = buildPageBundle(),
} = {}) {
  if (normalizeLineEndings(committed) !== normalizeLineEndings(fresh)) {
    throw new Error(
      'extension/src/page/bundle.js is stale: run `node scripts/build-page-bundle.mjs` and commit the result',
    );
  }
}

function readExtensionVersion() {
  return JSON.parse(readFileSync(join(EXTENSION_ROOT, 'manifest.json'), 'utf8')).version;
}

function run(command, args) {
  // One command string run by a shell: on Windows npx is npx.cmd, which needs a shell.
  const result = spawnSync([command, ...args].join(' '), { cwd: REPO_ROOT, stdio: 'inherit', shell: true });
  if (result.status !== 0) throw new Error(`${command} ${args[0]} failed (exit ${result.status})`);
}

function buildChromiumZip(version) {
  assertBundleFresh();
  run('npx', [
    '--yes', WEB_EXT, 'build',
    '--source-dir', 'extension',
    '--artifacts-dir', 'dist',
    '--filename', `lingotube-${version}-chromium.zip`,
    '--ignore-files', ...PACKAGE_IGNORE_GLOBS.map((glob) => quoteForShell(glob)),
    '--overwrite-dest',
  ]);
}

function buildSourceZip(version) {
  mkdirSync(ARTIFACTS_DIR, { recursive: true });
  run('git', ['archive', '--format=zip', `--output=dist/lingotube-${version}-source.zip`, 'HEAD']);
}

const runAsScript = process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url;
if (runAsScript) {
  const target = process.argv[2];
  const builders = { chromium: buildChromiumZip, source: buildSourceZip };
  if (!builders[target]) {
    console.error('Usage: node scripts/package-extension.mjs chromium|source');
    process.exit(2);
  }
  try {
    builders[target](readExtensionVersion());
  } catch (error) {
    console.error(error.message);
    process.exit(1);
  }
}
