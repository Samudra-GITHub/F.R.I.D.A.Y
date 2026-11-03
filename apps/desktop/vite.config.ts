import { spawn, type ChildProcess } from 'node:child_process';
import { existsSync } from 'node:fs';
import { connect } from 'node:net';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';

const EARTH_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '../gods-eye-view');
const EARTH_PORT = 4173;

const portInUse = (port: number) =>
  new Promise<boolean>((done) => {
    const socket = connect({ port, host: 'localhost' });
    socket.once('connect', () => {
      socket.destroy();
      done(true);
    });
    socket.once('error', () => done(false));
  });

/**
 * Starts the Earth app (apps/gods-eye-view) with this dev server and stops it on exit.
 * Runs a fixed executable with no shell, on localhost, and allows only this app to frame it.
 */
function earthServer(): Plugin {
  let child: ChildProcess | null = null;
  const stop = () => {
    child?.kill();
    child = null;
  };
  return {
    name: 'friday-earth-server',
    apply: 'serve',
    async configureServer(server) {
      const viteBin = join(EARTH_DIR, 'node_modules', 'vite', 'bin', 'vite.js');
      if (!existsSync(viteBin)) {
        server.config.logger.warn(
          '[earth] apps/gods-eye-view is not installed, so the Earth screen is unavailable. See docs/overhaul/handoff.md.'
        );
        return;
      }
      if (await portInUse(EARTH_PORT)) {
        server.config.logger.warn(
          `[earth] Port ${EARTH_PORT} is already in use. If the Earth screen stays blank, stop that server and restart this one.`
        );
        return;
      }
      child = spawn(process.execPath, [viteBin], {
        cwd: EARTH_DIR,
        stdio: 'inherit',
        env: {
          ...process.env,
          PORT: String(EARTH_PORT),
          GEV_EMBED_FRAME_ANCESTORS: 'http://localhost:5173 http://127.0.0.1:5173',
        },
      });
      child.on('error', (err) => server.config.logger.error(`[earth] Could not start: ${err.message}`));
      server.httpServer?.once('close', stop);
      process.once('exit', stop);
    },
  };
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), earthServer()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: false,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
