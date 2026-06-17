# 商业模式画布：从假设到验证

## 商业模式画布概述

商业模式画布（Business Model Canvas）由 Alexander Osterwalder 提出，用九个模块描述企业如何创造、传递和获取价值。

## 九大模块

### 1. 客户细分（Customer Segments）

我们为谁创造价值？

```
- 大众市场：面向所有用户
- 细分市场：特定行业或角色
- 利基市场：极小但高价值的市场
- 多边市场：同时服务两个群体（如平台）
```

### 2. 价值主张（Value Propositions）

我们解决什么问题？提供什么价值？

```
- 性能提升：RAG 查询延迟降低 50%
- 成本节约：替代人工搜索，节省 80% 时间
- 定制化：针对特定领域的 RAG 优化
- 可及性：让非技术用户也能使用 AI 搜索
```

### 3. 渠道通路（Channels）

如何触达客户？

```
- 线上渠道：官网、SEO、内容营销
- 销售渠道：直销、渠道商
- 社区渠道：开发者社区、开源项目
- 合作渠道：技术合作伙伴
```

### 4. 客户关系（Customer Relationships）

如何与客户建立和维持关系？

```
- 自助服务：在线文档、社区支持
- 专属服务：客户成功经理、技术支持
- 社区驱动：用户社区、知识共享
- 共创：与客户共同开发功能
```

### 5. 收入来源（Revenue Streams）

客户为什么付费？

```
- 订阅收入：月度/年度订阅费
- 按量计费：API 调用次数
- 增值服务：高级功能、优先支持
- 咨询服务：部署和优化咨询
```

### 6. 核心资源（Key Resources）

我们需要什么资源？

```
- 技术资源：RAG 引擎、向量数据库
- 人力资源：AI 工程师、产品经理
- 知识资源：领域知识、最佳实践
- 品牌资源：技术声誉、客户案例
```

### 7. 关键业务（Key Activities）

我们需要做什么？

```
- 平台开发：持续优化 RAG Pipeline
- 内容生产：技术博客、案例研究
- 客户成功：Onboarding、技术支持
- 社区运营：开发者社区、技术分享
```

### 8. 重要合作（Key Partnerships）

谁帮助我们？

```
- 技术伙伴：云服务商、模型提供商
- 渠道伙伴：系统集成商、咨询公司
- 战略伙伴：行业解决方案提供商
```

### 9. 成本结构（Cost Structure）

我们的主要成本是什么？

```
- 人力成本：工程师、产品、销售
- 基础设施：云服务、向量数据库
- API 成本：LLM、Embedding、Rerank
- 获客成本：营销、销售
```

## 验证方法

### 假设映射

```python
class BusinessModelValidator:
    """商业模式验证器"""

    def __init__(self, canvas: dict):
        self.canvas = canvas
        self.hypotheses = []

    def extract_hypotheses(self) -> list[dict]:
        """从画布中提取关键假设"""
        hypotheses = []

        # 客户细分假设
        hypotheses.append({
            "module": "customer_segments",
            "hypothesis": f"目标客户是 {self.canvas['customer_segments']}",
            "test": "客户访谈，验证痛点",
            "metric": "访谈中确认痛点的比例 > 70%",
        })

        # 价值主张假设
        hypotheses.append({
            "module": "value_propositions",
            "hypothesis": f"客户愿意为 {self.canvas['value_propositions']} 付费",
            "test": "MVP 测试，验证付费意愿",
            "metric": "付费转化率 > 3%",
        })

        # 收入来源假设
        hypotheses.append({
            "module": "revenue_streams",
            "hypothesis": f"客户愿意支付 {self.canvas['revenue_streams']} 的价格",
            "test": "定价测试，验证价格敏感度",
            "metric": "目标价格接受度 > 50%",
        })

        return hypotheses
```

## 关键事实

1. **商业模式画布由 Alexander Osterwalder 提出**，用九个模块描述企业如何创造、传递和获取价值
2. **九大模块**：客户细分、价值主张、渠道通路、客户关系、收入来源、核心资源、关键业务、重要合作、成本结构
3. **画布的核心是价值主张与客户细分的匹配**——为谁解决什么问题是商业模式的基础
4. **每个模块背后都是待验证的假设**，需要通过客户访谈、MVP 测试等方法逐一验证
5. **商业模式不是静态的**，应定期（每季度）审视和调整，特别是收入来源和客户细分
