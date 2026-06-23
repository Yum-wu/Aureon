import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { compression } from 'vite-plugin-compression2'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    compression({
      algorithms: ['gzip', 'brotliCompress'],
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
    // Vite 8 默认使用 Rolldown，推荐使用 rolldownOptions（rollupOptions 已弃用，作为别名仍可用）
    // 这里保留 manualChunks 函数形式（Rolldown 为 Rollup 兼容性仍支持）
    rolldownOptions: {
      output: {
        // 精细化手动分包：将大型第三方依赖拆分为独立 chunk，优化首屏加载
        manualChunks(id: string) {
          // React 核心（react + react-dom）
          if (id.includes('node_modules/react-dom') || id.includes('node_modules/react/')) {
            return 'vendor-react';
          }
          // React Router
          if (id.includes('node_modules/react-router-dom')) {
            return 'vendor-router';
          }
          // i18n 国际化
          if (id.includes('node_modules/i18next') || id.includes('node_modules/react-i18next')) {
            return 'vendor-i18n';
          }
          // 语法高亮（react-syntax-highlighter 体积较大，单独分包）
          if (id.includes('node_modules/react-syntax-highlighter')) {
            return 'vendor-syntax-highlight';
          }
          // Markdown 渲染链路（react-markdown + remark + rehype + unified 等）
          if (id.includes('node_modules/react-markdown') || id.includes('node_modules/remark-gfm') || id.includes('node_modules/unified') || id.includes('node_modules/remark-') || id.includes('node_modules/rehype-') || id.includes('node_modules/mdast-') || id.includes('node_modules/hast-')) {
            return 'vendor-md';
          }
          // Nivo 图表库
          if (id.includes('node_modules/@nivo')) {
            return 'vendor-nivo';
          }
          // TanStack Query
          if (id.includes('node_modules/@tanstack')) {
            return 'vendor-query';
          }
          // Zustand 状态管理
          if (id.includes('node_modules/zustand')) {
            return 'vendor-zustand';
          }
          // Floating UI（弹层定位）
          if (id.includes('node_modules/@floating-ui')) {
            return 'vendor-floating-ui';
          }
          // 日期处理（react-day-picker + date-fns）
          if (id.includes('node_modules/react-day-picker') || id.includes('node_modules/date-fns')) {
            return 'vendor-date';
          }
          // Sonner Toast 通知
          if (id.includes('node_modules/sonner')) {
            return 'vendor-sonner';
          }
        },
      },
    },
    cssCodeSplit: true,
    chunkSizeWarningLimit: 500,
    modulePreload: {
      polyfill: true,
    },
    reportCompressedSize: true,
  },
})
