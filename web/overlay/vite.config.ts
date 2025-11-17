import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  root: resolve(__dirname),
  // Use relative paths so index.html can be loaded from a subfolder in a Chrome extension
  base: './',
  build: {
    outDir: resolve(__dirname, '../../extension/overlay'),
    emptyOutDir: true,
  },
})
