import { defineConfig } from 'vite'
import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { compression } from 'vite-plugin-compression2'
import { createRequire } from 'node:module'
import type { Plugin } from 'vite'

// ESM 环境下通过 createRequire 获取 require.resolve 能力
const require = createRequire(import.meta.url)

// React Compiler 开关：默认开启，可通过环境变量 VITE_REACT_COMPILER_ENABLED=false 关闭
// 注意：React Compiler 需要以下 peer 依赖（见 package.json devDependencies）：
//   - babel-plugin-react-compiler
//   - @rolldown/plugin-babel
// 若未安装这些依赖，会自动跳过 React Compiler，不会导致构建失败
// @vitejs/plugin-react 6.0+ 不再支持 babel 配置项，需通过 reactCompilerPreset + @rolldown/plugin-babel 集成
const enableReactCompiler = process.env.VITE_REACT_COMPILER_ENABLED !== 'false'

// 动态加载 React Compiler 插件
// 依赖未安装时返回 null，不影响构建
function loadReactCompilerPlugin(): Plugin | null {
  if (!enableReactCompiler) return null
  try {
    require.resolve('@rolldown/plugin-babel')
    require.resolve('babel-plugin-react-compiler')
  } catch {
    // peer 依赖未安装，跳过 React Compiler
    return null
  }
  // 使用 require 加载，避免动态 import 触发 Vite 配置加载器的 UNRESOLVED_IMPORT 警告
  // @ts-ignore - @rolldown/plugin-babel 是可选 peer 依赖，类型声明可能不存在
  const babel = require('@rolldown/plugin-babel').default ?? require('@rolldown/plugin-babel')
  return babel({
    // @ts-ignore - reactCompilerPreset 类型要求 compilationMode，但运行时可选
    presets: [reactCompilerPreset({ target: '19' })],
  })
}

export default defineConfig(() => {
  // React Compiler — 自动记忆化优化（需 React 19+）
  // 仅在依赖已安装且未通过环境变量关闭时启用
  const reactCompilerPlugin = loadReactCompilerPlugin()

  return {
    plugins: [
      react(),
      // React Compiler 插件（未启用时为空，不影响构建）
      ...(reactCompilerPlugin ? [reactCompilerPlugin] : []),
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
      // 注意：Rolldown 推荐使用 output.codeSplitting.groups 替代已弃用的 advancedChunks
      // 这里保留 manualChunks 函数形式（Rolldown 为 Rollup 兼容性仍支持），改动最小、最安全
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
            // 注意：需放在 vendor-md 之前，避免被 markdown 规则先匹配
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
      // 合理的 chunk 大小警告阈值（原值 100 过于严格，几乎每个 chunk 都告警）
      chunkSizeWarningLimit: 500,
      // 模块预加载 polyfill，提升首屏 chunk 加载性能
      modulePreload: {
        polyfill: true,
      },
      // 报告 gzip 压缩后大小，便于评估真实传输体积
      reportCompressedSize: true,
    },
  }
})
