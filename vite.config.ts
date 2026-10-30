import { cpSync } from 'node:fs';
import { resolve } from 'node:path';
import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { build404, buildFallback, buildHeadTags, buildRobots, buildSitemap } from './src/lib/seo';

/**
 * Bakes the SEO surface into the shipped HTML.
 *
 * `src/data/acnd.ts` is the single source of truth for content, and this is
 * what keeps the crawlable version of the site honest: head tags, JSON-LD,
 * the no-JS fallback, robots.txt and the sitemap are all generated from that
 * same file, so they can never drift from what a visitor actually sees.
 */
const seoPlugin = (): Plugin => ({
  name: 'acnd-seo',
  transformIndexHtml: {
    order: 'pre',
    handler: (html) =>
      html.replace('<!--@HEAD-->', buildHeadTags()).replace('<!--@FALLBACK-->', buildFallback()),
  },
  generateBundle() {
    this.emitFile({ type: 'asset', fileName: 'robots.txt', source: buildRobots() });
    this.emitFile({ type: 'asset', fileName: 'sitemap.xml', source: buildSitemap() });
    // GitHub Pages serves this for any unknown path under the site.
    this.emitFile({ type: 'asset', fileName: '404.html', source: build404() });
  },
});

/**
 * Publishes the Down In Bossa release kit at /down-in-bossa/.
 *
 * The media lives once in the repo, under press/down-in-bossa/ where the
 * GitHub README links to it; this copies that folder (gallery page, reels,
 * banners) into the build as-is so the same files are also playable on the site.
 */
const pressKit = (): Plugin => ({
  name: 'acnd-press-kit',
  apply: 'build',
  writeBundle(options) {
    const outDir = options.dir ?? resolve(__dirname, 'dist');
    cpSync(resolve(__dirname, 'press/down-in-bossa'), resolve(outDir, 'down-in-bossa'), { recursive: true });
  },
});

/*
  Root-relative by default, which is what Vercel, Netlify and any plain static
  host want. A GitHub Pages *project* site serves from `/<repo>/` instead, so
  the deploy workflow sets BASE_PATH and SITE_URL rather than this file
  hard-coding one host's layout.
*/
// Vite requires a trailing slash; `actions/configure-pages` reports the path
// without one, so normalise rather than making the workflow do string surgery.
const rawBase = process.env.BASE_PATH || '/';
const base = rawBase.endsWith('/') ? rawBase : `${rawBase}/`;

export default defineConfig({
  base,
  plugins: [react(), seoPlugin(), pressKit()],
  build: {
    target: 'es2020',
    cssCodeSplit: false,
    reportCompressedSize: true,
    rollupOptions: {
      output: {
        // One vendor chunk (react) plus one app chunk keeps the request
        // waterfall to two files.
        manualChunks: (id) => (id.includes('node_modules/react') ? 'vendor' : undefined),
      },
    },
  },
});
