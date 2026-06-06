---
paths: ["src/**", "backend/**"]
---

# Code Quality Rules

## 前端（TypeScript/React）

- 组件用函数式 + hooks，不用 class component
- Props 用 interface 定义，export 到单独文件
- CSS 用 Tailwind utility classes，避免自定义 CSS
- 组件文件命名 PascalCase，工具文件命名 camelCase
- import 顺序：React → 第三方 → 内部组件 → hooks → utils → types → styles

## 后端（Python/FastAPI）

- 遵循 PEP 8，函数/变量 snake_case，类 PascalCase
- 所有公开函数必须有类型注解
- async 函数优先，IO 操作用 async/await
- FastAPI 路由用 Depends 做依赖注入
- 错误处理用 HTTPException，不要吞异常

## 通用

- 文件不超过 300 行，函数不超过 50 行
- 命名要有意义，避免缩写（除 i/j/k 循环变量）
- 注释解释 why 不是 what
- 死代码删掉，不要注释掉

## 测试

- 后端：pytest fixtures + parametrize
- 前端：@testing-library/react，测行为不测实现
- 测试文件放在对应目录的 tests/ 下，命名 test_*.py 或 *.test.ts
