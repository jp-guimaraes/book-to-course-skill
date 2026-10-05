// Course app made by course-to-appimage — Electron main process. Everything it needs is inside the AppImage.
//
// It does what the course folder's serve.py does, in Node: serves the course on 127.0.0.1, keeps progress in
// ~/.local/share/<app_id>/progress/progress.json and runs exercise tests ("Run tests") in editable copies of the
// exercises in ~/.local/share/<app_id>/exercises/. The page is shown in a window of the bundled Chromium.
//
// Options:  --paths            print where progress and exercises are kept
//           --open-exercises   open the exercises folder in the file manager
'use strict';
const { app, BrowserWindow, Menu, nativeTheme, shell } = require('electron');
const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

const HERE = __dirname;
const APP = JSON.parse(fs.readFileSync(path.join(HERE, 'app.json'), 'utf8'));
const COURSE = path.join(HERE, 'course');
const SEED = path.join(HERE, 'exercises');
const DATA = path.join(process.env.XDG_DATA_HOME || path.join(os.homedir(), '.local', 'share'), APP.app_id);
const EXERCISES = path.join(DATA, 'exercises');
const PROGRESS_DIR = path.join(DATA, 'progress');
const PROGRESS = path.join(PROGRESS_DIR, 'progress.json');
const WINDOW_STATE = path.join(DATA, 'window.json');
const MAX_BODY = 5 * 1024 * 1024;
const OUTPUT_LIMIT = 20000;
// a desktop session's PATH often misses where language toolchains live (shells add them in ~/.bashrc)
const EXTRA_PATH = ['~/.local/bin', '~/go/bin', '/usr/local/go/bin', '~/.cargo/bin', '~/.dotnet', '~/.deno/bin', '~/.bun/bin',
  '~/.volta/bin', '~/.sdkman/candidates/java/current/bin', '/usr/local/bin'];
const MIME = {
  '.html': 'text/html; charset=utf-8', '.htm': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
  '.webp': 'image/webp', '.ico': 'image/x-icon', '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf',
  '.mp3': 'audio/mpeg', '.mp4': 'video/mp4', '.webm': 'video/webm', '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/plain; charset=utf-8', '.wasm': 'application/wasm',
};

const args = process.argv.slice(1);
const out = s => fs.writeSync(1, s + '\n');  // synchronous: the process exits right after

// ---- exercises: editable copies in the user's data folder ------------------------------------------
function syncExercises() {
  if (!fs.existsSync(SEED)) return;
  for (const name of fs.readdirSync(SEED).sort()) {
    const src = path.join(SEED, name);
    if (!fs.statSync(src).isDirectory()) continue;
    let tests = [];
    try { tests = JSON.parse(fs.readFileSync(path.join(src, 'exercise.json'), 'utf8')).tests || []; } catch (e) { /* none */ }
    // exercise.json and the tests are refreshed on every start (a course update may fix them); the learner's files never are
    const refresh = new Set(['exercise.json', ...tests.filter(t => typeof t === 'string').map(t => path.normalize(t))]);
    (function walk(rel) {
      for (const ent of fs.readdirSync(path.join(src, rel), { withFileTypes: true })) {
        const r = path.join(rel, ent.name);
        if (ent.isDirectory()) { walk(r); continue; }
        const target = path.join(EXERCISES, name, r);
        if (fs.existsSync(target) && !refresh.has(path.normalize(r))) continue;
        fs.mkdirSync(path.dirname(target), { recursive: true });
        const mode = fs.statSync(path.join(src, r)).mode;
        fs.writeFileSync(target, fs.readFileSync(path.join(src, r)), { mode: mode & 0o111 ? 0o755 : 0o644 });
      }
    })('');
  }
}

// ---- local server: the same API as the course's serve.py -------------------------------------------
function json(res, code, obj) {
  const data = Buffer.from(JSON.stringify(obj));
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': data.length, 'Cache-Control': 'no-store' });
  res.end(data);
}

function which(cmd) {
  if (cmd.includes('/')) return fs.existsSync(cmd) ? cmd : null;
  for (const d of (process.env.PATH || '').split(path.delimiter)) {
    const p = path.join(d, cmd);
    try { fs.accessSync(p, fs.constants.X_OK); if (fs.statSync(p).isFile()) return p; } catch (e) { /* next */ }
  }
  return null;
}

function saveProgress(body, res) {
  fs.mkdirSync(PROGRESS_DIR, { recursive: true });
  const tmp = PROGRESS + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(body, null, 2));
  if (fs.existsSync(PROGRESS)) { try { fs.copyFileSync(PROGRESS, PROGRESS + '.bak'); } catch (e) { /* keep going */ } }
  fs.renameSync(tmp, PROGRESS);
  json(res, 200, { ok: true });
}

function runTests(body, res) {
  // only the folder name comes from the page; the command comes from exercise.json written when the course was built
  const name = String(body.dir || '');
  if (!/^[A-Za-z0-9_.-]+$/.test(name) || name.startsWith('.')) return json(res, 400, { error: 'bad exercise name' });
  const dir = path.join(EXERCISES, name);
  let cfg;
  try { cfg = JSON.parse(fs.readFileSync(path.join(dir, 'exercise.json'), 'utf8')); } catch (e) { return json(res, 404, { error: 'exercise not found' }); }
  const cmd = cfg.command;
  if (!(Array.isArray(cmd) && cmd.length && cmd.every(c => typeof c === 'string'))) return json(res, 500, { error: 'exercise.json has no valid command' });
  const timeout = Math.min(Math.max(parseInt(cfg.timeout, 10) || 60, 5), 300);
  if (!which(cmd[0])) {
    return json(res, 200, { ok: false, exit_code: 127, timed_out: false,
      output: "Program '" + cmd[0] + "' nie jest zainstalowany / is not installed.\n" });
  }
  const t0 = Date.now();
  let output = '', timedOut = false, done = false;
  const child = spawn(cmd[0], cmd.slice(1), { cwd: dir, detached: true, stdio: ['ignore', 'pipe', 'pipe'],
    env: Object.assign({}, process.env, { PYTHONDONTWRITEBYTECODE: '1', CI: '1' }) });
  const add = d => { if (output.length < 50 * OUTPUT_LIMIT) output += d.toString('utf8'); };
  child.stdout.on('data', add);
  child.stderr.on('data', add);
  const timer = setTimeout(() => { timedOut = true; try { process.kill(-child.pid, 'SIGKILL'); } catch (e) { /* gone */ } }, timeout * 1000);
  const finish = (code, extra) => {
    if (done) return;
    done = true;
    clearTimeout(timer);
    if (extra) output += extra;
    if (output.length > OUTPUT_LIMIT) output = output.slice(0, OUTPUT_LIMIT / 2) + '\n… [obcięto / truncated] …\n' + output.slice(-OUTPUT_LIMIT / 2);
    json(res, 200, { ok: code === 0 && !timedOut, exit_code: timedOut ? -1 : code, timed_out: timedOut, output,
      duration_ms: Date.now() - t0 });
  };
  child.on('error', e => finish(127, String(e.message || e) + '\n'));
  child.on('close', code => finish(code === null ? -1 : code));
}

function openExercise(body, res) {
  const name = String(body.dir || '');
  const dir = path.join(EXERCISES, name);
  if (!/^[A-Za-z0-9_.-]+$/.test(name) || name.startsWith('.') || !fs.existsSync(dir)) return json(res, 404, { error: 'exercise not found' });
  shell.openPath(dir).then(err => json(res, err ? 500 : 200, err ? { error: err } : { ok: true }));
}

// The page (the course's own player) tells the learner to work in "exercises/<dir>/" and to run "cd exercises/<dir>" —
// relative to the course folder, which the app doesn't have. Show the real folder instead, with an "open" button.
const OPEN_LABEL = { pl: 'Otwórz folder', pt: 'Abrir pasta', en: 'Open folder' };
function exercisePathsScript() {
  const root = JSON.stringify(EXERCISES);
  const label = JSON.stringify('📂 ' + (OPEN_LABEL[APP.ui_lang] || OPEN_LABEL.en));
  return `(() => {
    if (window.__courseAppPaths) return; window.__courseAppPaths = true;
    const ROOT = ${root}, q = s => "'" + s.replace(/'/g, "'\\\\''") + "'";
    const fix = () => document.querySelectorAll('.exercise code:not([data-app])').forEach(c => {
      const t = c.textContent; let m;
      if ((m = t.match(/^exercises\\/([A-Za-z0-9_.-]+)\\/$/))) {
        c.dataset.app = 1; c.textContent = ROOT + '/' + m[1] + '/';
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'btn ghost sm'; b.style.marginLeft = '8px'; b.textContent = ${label};
        b.onclick = () => fetch('api/open-exercise', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dir: m[1] }) });
        c.after(b);
      } else if ((m = t.match(/^cd exercises\\/([A-Za-z0-9_.-]+)/))) {
        c.dataset.app = 1; c.textContent = t.replace(m[0], 'cd ' + q(ROOT + '/' + m[1]));
        const box = c.parentNode, btn = box.querySelector('.copy-btn');
        if (btn) box.addEventListener('click', e => {  // capture on the parent runs before the player's own copy handler
          if (e.target !== btn) return; e.stopPropagation();
          const o = btn.textContent; navigator.clipboard.writeText(c.textContent).finally(() => { btn.textContent = '✓'; setTimeout(() => (btn.textContent = o), 1200); });
        }, true);
      }
    });
    fix(); new MutationObserver(fix).observe(document.body, { childList: true, subtree: true });
  })();`;
}

function serveFile(urlPath, res) {
  let rel;
  try { rel = decodeURIComponent(urlPath); } catch (e) { return json(res, 400, { error: 'bad path' }); }
  if (rel.endsWith('/')) rel += 'index.html';
  const file = path.normalize(path.join(COURSE, rel));
  if (!file.startsWith(COURSE + path.sep)) return json(res, 404, { error: 'not found' });
  fs.readFile(file, (err, data) => {
    if (err) return json(res, 404, { error: 'not found' });
    res.writeHead(200, { 'Content-Type': MIME[path.extname(file).toLowerCase()] || 'application/octet-stream',
      'Content-Length': data.length, 'Cache-Control': 'no-store' });
    res.end(data);
  });
}

function handle(req, res) {
  const host = (req.headers.host || '').replace(/:\d+$/, '').replace(/^\[|\]$/g, '');
  if (!['127.0.0.1', 'localhost', '::1'].includes(host)) return json(res, 403, { error: 'bad host' });
  const p = req.url.split('?', 1)[0];
  if (req.method === 'GET' || req.method === 'HEAD') {
    if (p === '/api/ping') return json(res, 200, { ok: true, server: 'course-helper', version: 1 });
    if (p === '/api/progress') {
      try { return json(res, 200, JSON.parse(fs.readFileSync(PROGRESS, 'utf8'))); } catch (e) { return json(res, 200, {}); }
    }
    return serveFile(p, res);
  }
  if (req.method !== 'POST') return json(res, 405, { error: 'method not allowed' });
  if (!(req.headers['content-type'] || '').includes('application/json')) return json(res, 415, { error: 'json only' });
  const chunks = [];
  let size = 0;
  req.on('data', c => { size += c.length; if (size <= MAX_BODY) chunks.push(c); });
  req.on('end', () => {
    let body;
    try { body = size <= MAX_BODY ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : null; } catch (e) { body = null; }
    if (!body || typeof body !== 'object' || Array.isArray(body)) return json(res, 400, { error: 'bad body' });
    try {
      if (p === '/api/progress') return saveProgress(body, res);
      if (p === '/api/run-tests') return runTests(body, res);
      if (p === '/api/open-exercise') return openExercise(body, res);
    } catch (e) {
      return json(res, 500, { error: String(e.message || e) });
    }
    json(res, 404, { error: 'not found' });
  });
}

function startServer() {
  // a stable port keeps the page's origin — and what it keeps in localStorage (e.g. the theme) — between launches
  const base = 20000 + parseInt(crypto.createHash('sha1').update(APP.app_id).digest('hex').slice(0, 8), 16) % 20000;
  return new Promise((resolve, reject) => {
    const tryPort = port => {
      if (port >= base + 40) return reject(new Error('no free port on 127.0.0.1'));
      const server = http.createServer(handle);
      server.once('error', () => tryPort(port + 1));
      server.listen(port, '127.0.0.1', () => resolve('http://127.0.0.1:' + port + '/'));
    };
    tryPort(base);
  });
}

// ---- window -----------------------------------------------------------------------------------------
let win = null;

function readState() {
  try { return JSON.parse(fs.readFileSync(WINDOW_STATE, 'utf8')); } catch (e) { return {}; }
}

function createWindow(url) {
  const st = readState();
  win = new BrowserWindow({
    width: st.width || 1200, height: st.height || 820, minWidth: 360, minHeight: 400,
    title: APP.name, autoHideMenuBar: true, show: false,
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#16171d' : '#ffffff',
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true, spellcheck: false },
  });
  if (st.maximized) win.maximize();
  const external = u => { if (/^(https?|mailto):/i.test(u)) shell.openExternal(u); };
  // links that leave the course open in the user's browser; target=_blank inside the course stays in this window
  win.webContents.setWindowOpenHandler(({ url: u }) => {
    if (u.startsWith(url)) win.loadURL(u); else external(u);
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (e, u) => { if (!u.startsWith(url)) { e.preventDefault(); external(u); } });
  win.webContents.on('before-input-event', (e, input) => {
    if (input.type !== 'keyDown') return;
    const wc = win.webContents;
    if (input.control || input.meta) {
      const k = input.key;
      if (k === '+' || k === '=') wc.setZoomFactor(Math.min(3, wc.getZoomFactor() + 0.1));
      else if (k === '-') wc.setZoomFactor(Math.max(0.5, wc.getZoomFactor() - 0.1));
      else if (k === '0') wc.setZoomFactor(1);
      else if (k.toLowerCase() === 'r') wc.reload();
      else return;
      e.preventDefault();
    } else if (input.key === 'F11') {
      win.setFullScreen(!win.isFullScreen());
      e.preventDefault();
    }
  });
  win.webContents.on('did-finish-load', () => {
    win.webContents.setZoomFactor(st.zoom || 1);
    // scrollbars and form controls follow the course's own theme toggle (the player sets data-theme on <html>)
    win.webContents.insertCSS(':root{color-scheme:light}:root[data-theme="dark"]{color-scheme:dark}');
    if (fs.existsSync(SEED)) win.webContents.executeJavaScript(exercisePathsScript()).catch(() => {});
  });
  win.once('ready-to-show', () => win.show());
  win.on('close', () => {
    const [width, height] = win.isMaximized() || win.isFullScreen() ? [st.width || 1200, st.height || 820] : win.getSize();
    try {
      fs.writeFileSync(WINDOW_STATE, JSON.stringify({ width, height, maximized: win.isMaximized(),
        zoom: Math.round(win.webContents.getZoomFactor() * 100) / 100 }));
    } catch (e) { /* not important */ }
  });
  win.loadURL(url);
}

// ---- start ------------------------------------------------------------------------------------------
if (args.includes('--paths')) {
  out('app:        ' + APP.name + ' ' + (APP.version || '') + ' (' + APP.app_id + ')');
  out('progress:   ' + PROGRESS);
  out('exercises:  ' + (fs.existsSync(SEED) ? EXERCISES : '(this course has no code exercises)'));
  app.exit(0);
} else {
  app.setPath('userData', path.join(DATA, 'electron'));
  app.commandLine.appendSwitch('class', APP.app_id);  // X11 WM_CLASS → matches StartupWMClass of the menu entry
  const extra = EXTRA_PATH.map(p => p.replace(/^~/, os.homedir()))
    .filter(p => fs.existsSync(p) && !(process.env.PATH || '').split(path.delimiter).includes(p));
  process.env.PATH = [process.env.PATH || '', ...extra].filter(Boolean).join(path.delimiter);

  if (!args.includes('--open-exercises') && !app.requestSingleInstanceLock()) {
    app.exit(0);  // already running: the first instance comes to the front (second-instance below)
  } else {
    app.on('second-instance', () => { if (win) { if (win.isMinimized()) win.restore(); win.focus(); } });
    app.on('window-all-closed', () => app.quit());
    app.whenReady().then(async () => {
      fs.mkdirSync(DATA, { recursive: true });
      syncExercises();
      if (args.includes('--open-exercises')) {
        await shell.openPath(fs.existsSync(EXERCISES) ? EXERCISES : DATA);
        return app.quit();
      }
      Menu.setApplicationMenu(null);
      createWindow(await startServer());
    }).catch(e => { console.error(e); app.exit(1); });
  }
}
