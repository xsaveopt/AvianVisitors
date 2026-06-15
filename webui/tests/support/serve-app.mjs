import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const webui = path.resolve(here, '..', '..');
const base = path.join(tmpdir(), 'av-e2e-runtime');
const port = process.env.AV_E2E_PORT || '8099';
const password = process.env.AV_E2E_PASSWORD || 'e2e-secret';
const user = process.env.AV_E2E_USER || 'admin';

const built = spawnSync('php', [path.join(here, 'build-runtime-cli.php'), base], { encoding: 'utf8' });
if (built.status !== 0) {
  process.stderr.write(built.stderr || 'failed to build runtime\n');
  process.exit(1);
}
const docroot = built.stdout.trim();

const build = spawnSync('npm', ['--prefix', webui, 'run', 'build'], { stdio: 'inherit' });
if (build.status !== 0) {
  process.exit(1);
}
const dist = path.join(webui, 'frontend', 'dist');

const server = spawn(
  'php',
  ['-S', `127.0.0.1:${port}`, '-t', dist, path.join(here, 'e2e-router.php')],
  {
    stdio: 'inherit',
    env: {
      ...process.env,
      AV_APP_DIR: docroot,
      AV_BIRDSONGS_DIR: path.join(base, 'BirdSongs'),
      AV_LOGS_DIR: path.join(base, 'logs'),
      AV_ADMIN_PASSWORD: password,
      AV_ADMIN_USER: user,
    },
  },
);

const shutdown = () => { try { server.kill(); } catch {} process.exit(0); };
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
server.on('exit', (code) => process.exit(code ?? 0));
