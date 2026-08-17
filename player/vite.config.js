import { defineConfig } from 'vite';
import { dirname, relative, resolve } from 'path';
import { cpSync, createReadStream, existsSync, mkdirSync, readdirSync, statSync, writeFileSync } from 'fs';

const recordingsDemoDir = resolve(__dirname, '../recordings-demo');
const recordingsDir = resolve(__dirname, '../recordings');

function walkCastFiles(dir) {
  const files = [];
  if (!existsSync(dir)) return files;
  for (const entry of readdirSync(dir)) {
    const fullPath = resolve(dir, entry);
    const stat = statSync(fullPath);
    if (stat.isDirectory()) {
      files.push(...walkCastFiles(fullPath));
      continue;
    }
    if (entry.endsWith('.cast')) files.push(fullPath);
  }
  return files;
}

function castsPlugin() {
  const virtualId = 'virtual:casts-config';
  const resolvedId = '\0' + virtualId;

  function scanCasts() {
    const entries = [];

    for (const absPath of walkCastFiles(recordingsDemoDir)) {
      const rel = relative(recordingsDemoDir, absPath).replace(/\\/g, '/');
      entries.push({
        project: 'demo',
        source: 'recordings-demo',
        castPath: rel,
        absPath,
        updatedAt: statSync(absPath).mtimeMs,
      });
    }

    for (const absPath of walkCastFiles(recordingsDir)) {
      const rel = relative(recordingsDir, absPath).replace(/\\/g, '/');
      const parts = rel.split('/');
      if (parts.length <= 1) {
        // Enforce project consistency: recordings must be namespaced by project slug.
        continue;
      }
      const project = parts[0];
      const castPath = parts.slice(1).join('/');
      entries.push({
        project,
        source: 'recordings',
        castPath,
        absPath,
        updatedAt: statSync(absPath).mtimeMs,
      });
    }

    const urls = new Set();
    return entries
      .map(entry => {
        const urlPath = `casts/${entry.project}/${entry.castPath}`.replace(/\\/g, '/');
        if (urls.has(urlPath)) return null;
        urls.add(urlPath);
        return {
          ...entry,
          urlPath,
          name: entry.castPath.replace(/\.cast$/i, ''),
          url: `./${urlPath}`,
        };
      })
      .filter(Boolean)
      .sort((a, b) => {
        if (a.project === 'demo' && b.project !== 'demo') return -1;
        if (a.project !== 'demo' && b.project === 'demo') return 1;
        if (a.project !== b.project) return a.project.localeCompare(b.project);
        return a.castPath.localeCompare(b.castPath);
      });
  }

  function buildCastMap(entries) {
    const map = new Map();
    for (const entry of entries) {
      map.set(entry.urlPath, entry.absPath);
    }
    return map;
  }

  function writeDistCasts(entries, distDir) {
    for (const entry of entries) {
      const target = resolve(distDir, entry.urlPath);
      mkdirSync(dirname(target), { recursive: true });
      cpSync(entry.absPath, target);
    }
  }

  return {
    name: 'casts-config',
    configureServer(server) {
      server.middlewares.use('/casts-index.json', (_req, res) => {
        const index = scanCasts().map(({project, source, name, url, updatedAt}) => ({
          project,
          source,
          name,
          url,
          updatedAt,
        }));
        res.setHeader('Content-Type', 'application/json');
        res.end(JSON.stringify(index));
      });
      server.middlewares.use('/casts', (req, res, next) => {
        const entries = scanCasts();
        const map = buildCastMap(entries);
        const urlPath = `casts/${req.url.replace(/^\//, '')}`;
        const file = map.get(urlPath);
        if (!file) {
          next();
          return;
        }
        res.setHeader('Content-Type', 'application/json');
        createReadStream(file).pipe(res);
      });
    },
    resolveId(id) {
      if (id === virtualId) return resolvedId;
    },
    load(id) {
      if (id !== resolvedId) return;
      const withTime = scanCasts().map(({project, source, name, url, updatedAt}) => ({
        project,
        source,
        name,
        url,
        updatedAt,
      }));
      return `export default ${JSON.stringify(withTime)};`;
    },
    closeBundle() {
      const distDir = resolve(__dirname, 'dist');
      mkdirSync(distDir, { recursive: true });
      const entries = scanCasts();
      writeDistCasts(entries, distDir);
      const index = entries.map(({project, source, name, url, updatedAt}) => ({
        project,
        source,
        name,
        url,
        updatedAt,
      }));
      writeFileSync(resolve(distDir, 'casts-index.json'), JSON.stringify(index, null, 2), 'utf-8');
    },
  };
}

export default defineConfig({
  base: './',
  server: {
    open: false,
    port: 8765,
    fs: {allow: ['..']},
  },
  preview: {
    open: false,
    port: 8765,
  },
  build: {
    outDir: 'dist',
    assetsInlineLimit: 0,
  },
  plugins: [castsPlugin()],
});
