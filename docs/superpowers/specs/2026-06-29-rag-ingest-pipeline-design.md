# RAG 文档摄取与分块设计

## 背景

当前系统已经支持 `md` / `txt` / `pdf` / `docx` / `xlsx` 上传，并在 `backend/app/rag/indexer.py` 中实现了 parent-child 分块与可选语义分块。但现有链路仍是“统一读入 + 统一切块”思路，类型差异没有被真正利用，导致：

- Markdown 的标题层级没有被稳定保留
- PDF 直接文本抽取，版面噪声和扫描件问题没有专门处理
- DOCX 的表格信息会丢失
- XLSX 被拍平成行文本，表格语义不够完整
- 缺少统一的清洗、去噪、质量门禁
- `.xls` 在 loader 中被提到，但上传路由并未放行，口径不一致

目标不是继续堆一个更复杂的 splitter，而是把“按类型抽取、清洗、切块、入库”做成一条清晰管线。

## 目标

1. 按文件类型分流处理，不再把所有文档交给同一条抽取路径
2. 保留文档结构信息，让 chunk 带足够元数据
3. 在入库前增加轻量但稳定的数据质量门禁
4. 保留现有 parent-child 与语义分块能力，作为通用兜底或二级切分
5. 统一上传口径，修掉 `.xls` 这类声明与实现不一致问题

## 非目标

- 不做大规模 OCR 产品化平台
- 不引入新的外部存储系统
- 不重写现有检索、rerank、生成链路
- 不为所有格式做无限兼容，只覆盖当前业务真正需要的类型

## 现状

### 现在已有的能力

| 类型 | 现状 |
|---|---|
| `md` | 解析 frontmatter，正文进入通用分块 |
| `txt` | 直接读取文本后分块 |
| `pdf` | 用 `pypdf` 抽全文文本 |
| `docx` | 读取段落文本 |
| `xlsx` | 按行转成 `col: value` 文本 |
| 分块 | `parent=1500/100`，`child=512/80`，支持可选语义分块 |
| 增强 | 可选 contextual prefix |

### 现有问题

| 问题 | 影响 |
|---|---|
| 没有类型分流抽取 | 不同格式被同一套逻辑对待，结构损失大 |
| 没有统一 normalizer | 空白、重复行、模板噪声会进入 chunk |
| 没有质量门禁 | 短块、空块、低信息密度块会污染索引 |
| 没有结构化 metadata 标准 | 来源展示、调试、评测都不够稳 |
| `.xls` 口径不一致 | 前后端支持声明容易误导用户 |

## 设计原则

1. 先保结构，再切块
2. 先分类型，再谈通用策略
3. 轻量规则优先，只有收益明确时才上重处理
4. 处理链路每层只做一件事
5. 让 chunk 可追溯、可回放、可评测

## 总体架构

```text
Upload / File Load
  -> Type Router
  -> Extractor
  -> Normalizer
  -> Chunk Policy
  -> Quality Gate
  -> Index Writer
```

### 模块职责

| 模块 | 职责 |
|---|---|
| Type Router | 根据扩展名和内容类型选择处理链路 |
| Extractor | 把原始文件转成结构化中间表示 |
| Normalizer | 做统一清洗、文本规范化、噪声过滤 |
| Chunk Policy | 按文件类型选择切块方式 |
| Quality Gate | 过滤坏块、短块、低信息密度块 |
| Index Writer | 写入向量库、BM25、元数据 |

## 文件类型策略

| 类型 | 抽取策略 | 切块策略 | 元数据重点 |
|---|---|---|---|
| `md` | 解析 frontmatter，保留标题层级、列表、代码块 | 标题优先，section 优先，递归切块兜底 | `section_path`, `heading_level` |
| `txt` | 统一空白归一、重复行过滤 | 递归字符切块为主 | `cleaned=true` |
| `pdf` | 页级抽取，低文本密度时走 OCR fallback，过滤页眉页脚 | 页/段优先，必要时递归补切 | `page_number`, `ocr_used` |
| `docx` | 段落 + 标题 + 表格一起抽 | 段落和标题优先，表格独立成块 | `paragraph_idx`, `table_idx` |
| `xlsx` | 按 sheet、表头、行组抽取，不直接拍平 | sheet/table 优先，行组为单位 | `sheet_name`, `row_range`, `table_idx` |

## 处理细节

### Markdown

- 解析 frontmatter
- 保留标题层级，生成 `section_path`
- 保留代码块、列表和引用块
- 切块时优先按标题与段落边界

### TXT

- 统一换行与空格
- 去掉连续空白行
- 可选去除模板行、页脚重复行
- 纯文本继续使用现有递归切块即可

### PDF

- 先做页级抽取
- 如果文本密度过低，判定为疑似扫描件，走 OCR fallback
- 尽量去掉页眉页脚、页码、重复装饰线
- 页级元数据必须保留，方便回查来源

### DOCX

- 除段落外，抽取表格
- 表格不要只拼成一坨文本，至少保留表头与单元格顺序
- 标题样式参与 section 组织

### XLSX

- 以 sheet 为最小组织单位
- 表头和行范围要保留
- 不建议把整个 sheet 直接拍平成一长串自然语言
- 更适合做“表块”而不是纯文本块

## 清洗规则

建议先上轻量通用规则，不要一开始就做过度复杂化：

| 规则 | 目的 |
|---|---|
| 去首尾空白 | 基础规范化 |
| 合并连续空行 | 减少碎片 |
| 去重复模板行 | 降噪 |
| 过滤超短块 | 防止无意义 chunk |
| 过滤低字符密度块 | 去掉表格残片、乱码、装饰线 |
| 统一标点与空格 | 提升检索一致性 |
| 可选脱敏 | 避免敏感信息入库 |

## Chunk Policy

### 默认策略

- `md`：标题优先
- `txt`：递归字符切块
- `pdf/docx`：页/段/章节优先
- `xlsx`：表格优先

### 通用兜底

现有 parent-child 分块继续保留，但定位为：

1. 类型策略失败时的 fallback
2. 大文档的二级补切
3. 通用的稳定兜底方案

现有语义分块也保留，但默认仍关闭，只在抽取质量足够稳定后用于特定类型或特定目录。

## Quality Gate

入库前至少做这些检查：

- 空块直接丢弃
- 超短块丢弃
- 重复块丢弃
- 乱码块丢弃
- 低信息密度块丢弃
- 超过大小阈值的块重新切分

建议将这些规则做成独立的 gate，而不是散在各个 extractor 里。

### 已实现的质量门禁 API

```python
# quality.py
DEFAULT_MIN_CHUNK_LEN = 100            # 最短有效块长度
DEFAULT_MIN_UNIQUE_RATIO = 0.3         # 至少 30% 不重复字符

def is_valid_chunk(text, *, min_len=100) -> bool
    # 拒绝空 / 超短块

def is_informative_chunk(text, *, min_unique_ratio=0.3) -> bool
    # 拒绝低信息密度块（全相同字符 / 纯标点）

def deduplicate_chunks(chunks, *, key="text") -> list[dict]
    # 按文本去重，保留顺序
```

所有门禁在 `build_chunks` 管线出口统一调用。未实现的（脱敏、统一标点）保持为后续可选增强。

## 元数据标准

每个 chunk 建议至少携带：

| 字段 | 说明 |
|---|---|
| `source` | 原文件名 |
| `title` | 文档标题 |
| `slug` | 文档标识 |
| `file_type` | 文件类型 |
| `language` | 语言 |
| `section_path` | Markdown/章节路径 |
| `page_number` | PDF 页码 |
| `sheet_name` | Excel sheet 名 |
| `row_range` | Excel 行范围 |
| `table_idx` | 表格索引 |
| `parent_idx` | 父块索引 |
| `chunk_idx` | 子块索引 |
| `ocr_used` | 是否使用 OCR |

## 口径统一

`.xls` 目前存在声明与路由不一致问题。设计上建议先统一为：

- 只支持当前链路真正稳定的格式
- 如果要支持老式 `.xls`，必须补独立兼容链路和测试

在没有稳定实现之前，不建议继续在文档里暗示已经完整支持。

## 类型转换（实施中发现的关键问题）

`add_to_index()` 期望 `List[Dict]`（dict 格式），但 `build_chunks` 输出是 `list[ChunkRecord]`（dataclass）。

```python
# models.py
@dataclass
class ChunkRecord:
    text: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "metadata": self.metadata}

# pipeline.py
def chunks_to_dicts(chunks: list[ChunkRecord]) -> list[dict]:
    return [c.to_dict() for c in chunks]
```

`run_incremental_index` 调用链路：`build_chunks → chunks_to_dicts → add_to_index`。  
`run_index_pipeline`（旧路径）仍直接操作 dict，暂未迁移。

## 错误处理

| 场景 | 处理方式 |
|---|---|
| 文件为空 | 直接报错，拒绝入库 |
| 不支持的格式 | 明确返回类型错误 |
| OCR / 解析失败 | 记录失败原因，整文件回退或跳过 |
| 单个表格抽取失败 | 不阻断整个文档，保留其余内容 |
| 质量门禁拦截 | 记录拦截统计，方便调优 |

## 观测指标

建议补这些指标：

- 按类型的成功率
- 按类型的 chunk 数量分布
- 平均 chunk 长度
- 质量门禁拦截率
- OCR 触发率
- 表格抽取成功率
- 解析失败原因分布

## 测试策略

| 测试 | 覆盖 |
|---|---|
| 单元测试 | 各类型 extractor 的基础输出 |
| 单元测试 | normalizer 对空白、重复行、短块的处理 |
| 单元测试 | quality gate 的拦截逻辑 |
| 集成测试 | 上传后索引的 chunk 元数据完整性 |
| 集成测试 | PDF/DOCX/XLSX 的典型样本 |
| 回归测试 | `.xls` 口径统一后的行为 |

## 实施顺序

1. ✅ 统一上传类型口径（拒绝 `.xls`，仅支持 md/txt/pdf/docx/xlsx）
2. ✅ 拆出 normalizer 和 quality gate（normalizer.py + quality.py）
3. ✅ 实现按类型 extractor（extractors.py：5 类型独立抽取）
4. ✅ 给 chunk 补标准 metadata（section_path、file_type、chunk_idx 等）
5. ✅ 调整 chunk policy 的段落聚合（policy.py：段落边界 + 512 char 上限）
6. ✅ 补测试与观测指标（3 个测试文件，11 个回归测试）
7. ⬜ 观测指标接入（预留）
8. ⬜ run_index_pipeline 迁移到新管线（旧路径暂保留）

## 风险

| 风险 | 说明 | 缓解 |
|---|---|---|
| 过度工程化 | 一开始就做太重的抽取链 | 先做轻量规则和常用格式 |
| OCR 成本过高 | 扫描件处理慢且贵 | 仅在低文本密度时触发 |
| 表格语义损失 | XLSX/DOCX 表格仍可能被拍扁 | 表格单独成块并保留行列信息 |
| 口径漂移 | 文档和代码支持范围不一致 | 统一支持列表和测试 |

## 结论

当前系统的核心短板不是“不会切块”，而是“没有按文件类型建立稳定的摄取语义”。  
这次改造的正确方向是：**类型分流抽取 + 轻量清洗 + 结构化 metadata + 质量门禁 + 通用兜底分块**。  
这样改完，后续无论是检索质量、来源展示还是问题排查，都会顺很多。
