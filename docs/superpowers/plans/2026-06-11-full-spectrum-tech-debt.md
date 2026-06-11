# Full-Spectrum Tech Debt Fix Plan

**Date**: 2026-06-11
**Scope**: ~20 items across config/RAG/Docker/test/exception/security/benchmark/hygiene
**Delivery**: Single PR, staged commits
**Testing**: Backend `pytest` + frontend `npm test`

---

## 阶段 1: Config — 按域拆分 + DI

### 1.1 拆 Settings 基类

将 `backend/app/config.py` 中单一 `Settings(BaseSettings)` 重构为：

```
Settings(BaseSettings)
├── app: AppSettings(BaseModel)        # debug, env, CORS origins
├── auth: AuthSettings(BaseModel)      # API_AUTH_KEY, JWT_SECRET, SSO_*
├── database: DatabaseSettings(BaseModel)  # SQLite path, pool
├── vector_store: VectorStoreSettings(BaseModel)  # Qdrant URL/collection/API key, embedding model
├── rerank: RerankSettings(BaseModel)  # rerank model, candidates, threshold
├── cache: CacheSettings(BaseModel)    # Redis URL, TTL
```

顶层 `Settings` 使用 `env_nested_delimiter='__'`：
- `VECTOR_STORE__QDRANT_URL=...`
- `RERANK__ENABLED=true`

### 1.2 消除 os.environ 旁路

3 处 `os.environ.get(...)` 改为引用 `settings`：

| 文件 | 行 | 替换为 |
|------|------|--------|
| `backend/app/main.py` | 16 | `settings.rerank.enabled` |
| `backend/app/rag/embed_gpu.py` | 199 | `settings.rerank.enabled` |
| `backend/app/rag/vector_store.py` | 1083 | `settings.rerank.enabled` |

### 1.3 依赖注入接入

- `backend/app/config.py` 新增 `get_settings()` FastAPI 依赖（返回 `Settings` 单例）
- `backend/app/routers/` 下所有路由函数通过 `Depends(get_settings)` 注入
- 非路由模块（工具、RAG、Agent 等）函数签名加 `settings: Settings` 参数
- `from app.config import settings`（~40 处）逐一改为函数参数传递

### 1.4 测试适配

- `tests/conftest.py` 或各测试文件通过 `with override()` 注入 mock settings
- `tests/test_audit.py` 中 `get_audit_stats` 调用不用 settings，无需改动

---

## 阶段 2: RAG 遗留清理

### 2.1 vector_store.py

- 删除 `if vector_backend == "chroma"` 条件分支
- `if backend == "chroma"` 分支体改为 `raise NotImplementedError("chroma removed")` 或直接删除
- Chroma 特有函数保留存根或删除：
  - `_chroma_search()`, `_chroma_delete()`, `_migrate_from_chroma()` 等 → 删除
  - 客户端初始化 `self._chroma_client = None` 或删除
- 保留 `load_index()` 签名但 Chroma 分支内容移除

### 2.2 tools/__init__.py

- `backend/app/tools/__init__.py:15` 删除或注释掉 Chroma `load_index()` 调用

### 2.3 langgraph/graph.py

- `backend/app/langgraph/graph.py:89` 硬编码 `"chroma_knowledge_base"` → 改为 `"qdrant_knowledge_base"` 或从 settings 读取

### 2.4 benchmark/config.py

- `backend/benchmark/config.py:84` `vector_backend = "chroma"` → `"qdrant"`

---

## 阶段 3: Dockerfile 修复

### 3.1 Dockerfile.test L8

`COPY --from=frontend-builder /app/dist /app/static/web` 改为直接复制本地构建产物或写死正确路径映射。

最小修复：引用 `Dockerfile` 实际存在的阶段名，或直接 `COPY ./backend/static /app/static`。

---

## 阶段 4: 测试修复

### 4.1 get_audit_stats 加 now 参数

`backend/app/audit/service.py`：

```python
def get_audit_stats(tenant_id: str = "default", now: Optional[datetime] = None) -> AuditStatsResponse:
    now = now or datetime.now(timezone.utc)
    one_hour_ago = (now - timedelta(hours=1)).isoformat()
    one_day_ago = (now - timedelta(hours=24)).isoformat()
```

### 4.2 test_audit.py

```python
now_iso = "2026-06-10T00:00:00+00:00"
now_dt = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)  # 确保 00:00 在 24h 窗口内
stats = get_audit_stats(tenant_id=tenant, now=now_dt)
assert stats.recent_count_24h == 3
```

### 4.3 pytest.ini 清理

删除 `--ignore=tests/test_audit.py` 配置（如有）。

---

## 阶段 5: 异常体系

### 5.1 concurrency.py

`backend/app/concurrency.py:49,72`：

```python
# 原
raise HTTPException(status_code=429, detail="..."
# 改
raise RateLimitException(...)  # 继承自 AureonException
```

（使用现有的 `AureonException` 子类，或新增 `RateLimitException`）

---

## 阶段 6: Docker 安全

### 6.1 docker-compose.yml 凭据

```yaml
environment:
  - REDIS_PASSWORD=${REDIS_PASSWORD:-aureon_redis_dev}
  - ES_PASSWORD=${ES_PASSWORD:-aureon_es_dev}
```

### 6.2 .env.example

创建 `backend/.env.example`（或根 `.env.example`）：

```env
REDIS_PASSWORD=change_me_in_production
ES_PASSWORD=change_me_in_production
```

### 6.3 .gitignore

确认 `.env` 在 `.gitignore` 中。

---

## 阶段 7: Benchmark 配置

### 7.1 benchmark/config.py

`backend/benchmark/config.py:84`: `"chroma"` → `"qdrant"`。

---

## 阶段 8: P2 杂项

### 8.1 act() 警告

8 个前端测试文件中的 `act()` 包裹或等待，改为 `waitFor` 模式。具体：

- 检查各测试文件中的 render/update 调用，用 `await` 包装或 `waitFor` 替换 `act()` 回调

### 8.2 TODO 清理

5 处 TODO：

| 文件 | TODO | 处理 |
|------|------|------|
| `app/routers/rag.py` | analytics integration | 添加 logger.info 或删除 TODO |
| `app/routers/crew.py` | missing stats | 添加 stub 或删除 TODO |
| `app/rag/qa_chain.py` | adaptive threshold tuning | 留为注释，删除 TODO 标记 |
| `app/rag/vector_store.py` | cache TTL | 改为 settings 驱动 |
| `app/observability/metrics.py` | prometheus | 删除或实现 |

### 8.3 Chroma 迁移函数删除

`vector_store.py` 中的 `_migrate_from_chroma()` 函数删除（2.1 已覆盖）。

---

## 执行顺序

```
Phase 1 (Config)       ──────────┐
                                  ├──→ Phase 4 (Test) ──→ Phase 5 (Exception) ──→ Phase 8 (P2)
Phase 2 (RAG)          ──────────┤
                                  │
Phase 3 (Docker)       ──────────┼──→ Phase 6 (Security)
                                  │
Phase 7 (Benchmark)    ──────────┘
```

实际按依赖顺序实施：Config → RAG → Docker → Test → Exception → Security → Benchmark → P2。

---

## 验证

每阶段完工后运行：

```bash
cd backend && python -m pytest tests/ -v --tb=short -x
```

确认 0 failed（含 `test_audit.py`）。

```bash
npm test -- --run
```

确认无新增失败。

```bash
docker compose build
```

确认 Dockerfile 构建通过。
