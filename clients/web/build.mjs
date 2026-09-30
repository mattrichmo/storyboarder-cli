/** Deterministic, dependency-light TypeScript build. No CDN or runtime Node requirement. */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
let ts;
try {
  ts = require('typescript');
} catch {
  if (!process.env.STORYBOARDER_TYPESCRIPT_PATH) throw new Error('Run npm ci in clients/web before building.');
  ts = require(process.env.STORYBOARDER_TYPESCRIPT_PATH);
}

const root = path.dirname(fileURLToPath(import.meta.url));
const src = path.join(root, 'src');
const dest = path.resolve(root, '../../src/storyboarder/static');
const digest = (value) => crypto.createHash('sha256').update(value).digest('hex');

function walk(dir) {
  return fs.readdirSync(dir).sort().flatMap((name) => {
    const file = path.join(dir, name);
    return fs.statSync(file).isDirectory() ? walk(file) : [file];
  });
}

function writeAtomic(target, content) {
  fs.mkdirSync(path.dirname(target), { recursive: true });
  const temporary = `${target}.tmp-${process.pid}-${crypto.randomBytes(6).toString('hex')}`;
  try {
    fs.writeFileSync(temporary, content);
    fs.renameSync(temporary, target);
  } finally {
    fs.rmSync(temporary, { force: true });
  }
}

function publishAsset(source, target) {
  const content = fs.readFileSync(source);
  if (fs.existsSync(target) && digest(fs.readFileSync(target)) === digest(content)) return;
  writeAtomic(target, content);
}

function pruneOldBundles(currentNames) {
  const assetDir = path.join(dest, 'assets');
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  for (const name of fs.readdirSync(assetDir)) {
    if (!/^app-[a-f0-9]{12}\.(?:js|css)$/.test(name) || currentNames.has(name)) continue;
    const file = path.join(assetDir, name);
    if (fs.statSync(file).mtimeMs < cutoff) fs.rmSync(file, { force: true });
  }
  const legacyCss = path.join(assetDir, 'app.css');
  if (fs.existsSync(legacyCss) && fs.statSync(legacyCss).mtimeMs < cutoff) fs.rmSync(legacyCss, { force: true });
}

function build() {
  const configFile = ts.readConfigFile(path.join(root, 'tsconfig.json'), ts.sys.readFile);
  if (configFile.error) {
    console.error(ts.flattenDiagnosticMessageText(configFile.error.messageText, '\n'));
    return false;
  }
  const config = ts.parseJsonConfigFileContent(configFile.config, ts.sys, root);
  const program = ts.createProgram(config.fileNames, config.options);
  const diagnostics = ts.getPreEmitDiagnostics(program);
  if (diagnostics.length) {
    console.error(ts.formatDiagnosticsWithColorAndContext(diagnostics, {
      getCanonicalFileName: (file) => file,
      getCurrentDirectory: () => root,
      getNewLine: () => '\n',
    }));
    return false;
  }
  if (process.argv.includes('--check')) {
    console.log('TypeScript: no errors.');
    return true;
  }

  const modules = walk(src)
    .filter((file) => /\.tsx?$/.test(file) && !file.endsWith('.d.ts'))
    .map((file) => {
      const id = path.relative(src, file).replaceAll(path.sep, '/').replace(/\.tsx?$/, '');
      const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
        compilerOptions: { ...config.options, noEmit: false, sourceMap: false },
      }).outputText;
      return `${JSON.stringify(id)}:function(require,module,exports){\n${code}\n}`;
    });

  const runtime = `(function(){'use strict';\nconst modules={${modules.join(',\n')}};\nconst cache={};function load(id){if(cache[id])return cache[id].exports;if(!modules[id])throw Error('Missing app module '+id);const m=cache[id]={exports:{}};function req(relative){const parts=id.split('/');parts.pop();for(const p of relative.split('/')){if(p==='.'||!p)continue;if(p==='..')parts.pop();else parts.push(p)}return load(parts.join('/').replace(/\\.js$/,''));}modules[id](req,m,m.exports);return m.exports;}load('main');})();\n`;
  const appHash = digest(runtime).slice(0, 12);
  const css = fs.readFileSync(path.join(src, 'styles.css'));
  const cssHash = digest(css).slice(0, 12);
  const appName = `app-${appHash}.js`;
  const cssName = `app-${cssHash}.css`;
  fs.mkdirSync(dest, { recursive: true });
  const stage = fs.mkdtempSync(path.join(os.tmpdir(), 'storyboarder-web-build-'));

  try {
    const stagedAssets = path.join(stage, 'assets');
    fs.mkdirSync(stagedAssets, { recursive: true });
    fs.writeFileSync(path.join(stagedAssets, appName), runtime);
    fs.writeFileSync(path.join(stagedAssets, cssName), css);
    fs.copyFileSync(path.join(root, 'vendor/react-runtime.js'), path.join(stagedAssets, 'react-runtime.js'));
    fs.copyFileSync(path.join(root, 'vendor/THIRD_PARTY_LICENSES.txt'), path.join(stage, 'THIRD_PARTY_LICENSES.txt'));
    fs.copyFileSync(path.join(root, 'favicon.svg'), path.join(stage, 'favicon.svg'));

    const index = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f5f3ed"><title>Storyboarder — production desk</title><link rel="icon" href="/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="/assets/${cssName}"></head><body><div id="root"><p class="boot">Opening your production desk…</p></div><noscript>Storyboarder requires JavaScript. The CLI and TUI work without a browser.</noscript><script src="/assets/react-runtime.js"></script><script src="/assets/${appName}"></script></body></html>`;
    const buildInfo = {
      appVersion: '1.0.0',
      typescript: ts.version,
      react: '18.2.0',
      entry: `assets/${appName}`,
      style: `assets/${cssName}`,
      sha256: digest(runtime),
      style_sha256: digest(css),
    };

    fs.mkdirSync(path.join(dest, 'assets'), { recursive: true });
    publishAsset(path.join(stagedAssets, appName), path.join(dest, 'assets', appName));
    publishAsset(path.join(stagedAssets, cssName), path.join(dest, 'assets', cssName));
    publishAsset(path.join(stagedAssets, 'react-runtime.js'), path.join(dest, 'assets/react-runtime.js'));
    publishAsset(path.join(stage, 'THIRD_PARTY_LICENSES.txt'), path.join(dest, 'THIRD_PARTY_LICENSES.txt'));
    publishAsset(path.join(stage, 'favicon.svg'), path.join(dest, 'favicon.svg'));

    // The HTML pointer changes only after every referenced asset has been published.
    writeAtomic(path.join(dest, 'index.html'), index);
    writeAtomic(path.join(dest, 'build.json'), `${JSON.stringify(buildInfo, null, 2)}\n`);
    pruneOldBundles(new Set([appName, cssName]));
    console.log(`Built ${modules.length} application modules → ${dest}`);
    return true;
  } finally {
    fs.rmSync(stage, { recursive: true, force: true });
  }
}

if (!build()) process.exitCode = 1;
if (process.argv.includes('--watch')) {
  console.log('Watching source. Run storyboarder ui in another terminal; refresh the browser after a rebuild.');
  let timer;
  fs.watch(src, { recursive: true }, () => {
    clearTimeout(timer);
    timer = setTimeout(() => build(), 160);
  });
}
