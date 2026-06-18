import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { compression } from 'vite-plugin-compression2'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    compression({
      algorithms: ['gzip'],
      threshold: 1024,
      deleteOriginalAssets: false,
    }),
  ],
  server: {
    host: '0.0.0.0',
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes('node_modules/react-dom') || id.includes('node_modules/react/')) {
            return 'vendor-react';
          }
          if (id.includes('node_modules/react-router-dom')) {
            return 'vendor-router';
          }
          if (id.includes('node_modules/i18next') || id.includes('node_modules/react-i18next')) {
            return 'vendor-i18n';
          }
          if (id.includes('node_modules/react-markdown') || id.includes('node_modules/remark-gfm') || id.includes('node_modules/react-syntax-highlighter') || id.includes('node_modules/unified') || id.includes('node_modules/remark-') || id.includes('node_modules/rehype-') || id.includes('node_modules/mdast-') || id.includes('node_modules/hast-')) {
            return 'vendor-md';
          }
          if (id.includes('node_modules/@nivo')) {
            return 'vendor-nivo';
          }
        },
      },
    },
    cssCodeSplit: true,
    chunkSizeWarningLimit: 100,
  },
})
