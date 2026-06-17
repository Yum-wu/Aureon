# 多模态 RAG：图文混合检索与生成

## 多模态 RAG 的需求

传统 RAG 仅处理文本，但企业知识库中包含大量图表、截图、PDF 扫描件等非文本内容。多模态 RAG 扩展了检索和生成的范围，支持**图文混合检索**——用户可以用文本查询检索图片，或用图片查询检索相关文档。

## 架构设计

### 整体架构

```
输入（文本/图片）→ 多模态编码 → 联合向量空间 → 检索 → 多模态生成
```

### 三种实现路径

1. **文本中心**：图片 → OCR/描述 → 文本检索
2. **向量中心**：图片 → 视觉编码 → 联合向量检索
3. **混合**：文本 + 视觉双编码 → 多模态融合检索

## 图片处理 Pipeline

### 图片描述生成

```python
async def generate_image_description(
    image_url: str,
    llm,  # 多模态 LLM（如 GPT-4V）
) -> str:
    """生成图片的文字描述"""
    prompt = """请详细描述这张图片的内容，包括：
1. 图片的主要内容和主题
2. 图表中的数据和趋势（如果是图表）
3. 关键文字和标注
4. 图片的上下文和用途"""

    response = await llm.ainvoke(
        messages=[
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]}
        ]
    )
    return response


async def process_image_document(
    image_url: str,
    llm,
    embedder,
    vectorstore,
) -> dict:
    """处理图片文档：生成描述 + 编码 + 索引"""
    # 1. 生成图片描述
    description = await generate_image_description(image_url, llm)

    # 2. OCR 提取文字
    ocr_text = await extract_text_from_image(image_url)

    # 3. 合并描述和 OCR 文字
    combined_text = f"图片描述：{description}\n\nOCR 文字：{ocr_text}"

    # 4. 编码并索引
    embedding = await embedder.aembed_query(combined_text)
    await vectorstore.aadd_embedding(
        text=combined_text,
        embedding=embedding,
        metadata={"type": "image", "url": image_url},
    )

    return {"description": description, "ocr_text": ocr_text}
```

### OCR 处理

```python
async def extract_text_from_image(image_url: str) -> str:
    """从图片中提取文字（OCR）"""
    import httpx

    async with httpx.AsyncClient() as client:
        # 调用 OCR API
        response = await client.post(
            "https://api.dashscope.com/v1/services/ocr/general",
            json={"image": image_url},
            headers={"Authorization": f"Bearer {API_KEY}"},
        )

    result = response.json()
    text_blocks = result.get("output", {}).get("results", [])
    return "\n".join([block["text"] for block in text_blocks])
```

## 多模态嵌入模型

### CLIP 模型

CLIP（Contrastive Language-Image Pre-training）由 OpenAI 发布，将图片和文本映射到同一向量空间：

```python
import torch
from transformers import CLIPModel, CLIPProcessor

model = CLIPModel.from_pretrained("openai/clip-vit-large-patch14")
processor = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14")

def encode_image(image) -> torch.Tensor:
    """编码图片"""
    inputs = processor(images=image, return_tensors="pt")
    with torch.no_grad():
        features = model.get_image_features(**inputs)
    return features / features.norm(p=2, dim=-1, keepdim=True)

def encode_text(text: str) -> torch.Tensor:
    """编码文本"""
    inputs = processor(text=text, return_tensors="pt", padding=True)
    with torch.no_grad():
        features = model.get_text_features(**inputs)
    return features / features.norm(p=2, dim=-1, keepdim=True)

# 跨模态检索：文本查询图片
text_embedding = encode_text("RAG 架构图")
image_embedding = encode_image(image)
similarity = torch.dot(text_embedding.squeeze(), image_embedding.squeeze())
```

### 多模态向量库

```python
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams

# 创建多模态向量库
client = QdrantClient("localhost", port=6333)

client.create_collection(
    collection_name="multimodal_docs",
    vectors_config={
        "text": VectorParams(size=1024, distance="Cosine"),  # 文本嵌入
        "image": VectorParams(size=768, distance="Cosine"),  # 图片嵌入（CLIP）
    },
)

# 插入图文文档
point = PointStruct(
    id=1,
    vector={
        "text": text_embedding.tolist(),
        "image": image_embedding.tolist(),
    },
    payload={
        "type": "image_with_text",
        "text": "RAG 架构图：包含查询路由、检索、Rerank、生成四个模块",
        "image_url": "https://example.com/rag-architecture.png",
    },
)
```

## PDF 扫描件处理

### 处理流程

```
PDF 扫描件 → 页面分割 → OCR + 图片描述 → 文本合并 → 编码索引
```

```python
async def process_scanned_pdf(
    pdf_path: str,
    llm,
    embedder,
    vectorstore,
    ocr_service,
) -> dict:
    """处理 PDF 扫描件"""
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    chunks = []

    for page_num in range(len(doc)):
        page = doc[page_num]

        # 1. 提取图片
        images = page.get_images()
        page_text_parts = []

        # 2. OCR 提取文字
        page_image = page.get_pixmap()
        ocr_text = await ocr_service.extract(page_image)
        page_text_parts.append(f"OCR 文字：{ocr_text}")

        # 3. 图片描述
        for img in images:
            description = await generate_image_description(img, llm)
            page_text_parts.append(f"图片描述：{description}")

        # 4. 合并页面内容
        page_content = f"\n\n".join(page_text_parts)
        chunks.append({
            "content": page_content,
            "page": page_num + 1,
            "source": pdf_path,
        })

    # 5. 编码并索引
    texts = [chunk["content"] for chunk in chunks]
    embeddings = await embedder.aembed_documents(texts)
    await vectorstore.aadd_embeddings(
        texts=texts,
        embeddings=embeddings,
        metadatas=[{"page": c["page"], "source": c["source"]} for c in chunks],
    )

    return {"total_pages": len(doc), "total_chunks": len(chunks)}
```

## 多模态生成

### 图文混合答案

```python
async def multimodal_generate(
    query: str,
    docs: list,
    llm,
) -> str:
    """多模态生成：包含图片引用的答案"""
    # 分离文本和图片文档
    text_docs = [d for d in docs if d.metadata.get("type") != "image"]
    image_docs = [d for d in docs if d.metadata.get("type") == "image"]

    # 构建上下文
    text_context = "\n\n".join([d.page_content for d in text_docs])
    image_context = "\n\n".join([
        f"[图片：{d.page_content}，链接：{d.metadata.get('image_url', '')}]"
        for d in image_docs
    ])

    prompt = f"""基于以下文本和图片信息回答问题。如果相关，请在答案中引用图片。

文本信息：
{text_context}

图片信息：
{image_context}

问题：{query}

回答："""

    return await llm.ainvoke(prompt)
```

## 关键事实

1. **多模态 RAG 支持图文混合检索**，三种实现路径：文本中心（OCR+描述）、向量中心（视觉编码）、混合（双编码融合）
2. **CLIP 模型将图片和文本映射到同一向量空间**，实现跨模态检索——文本查询图片、图片查询文档
3. **PDF 扫描件处理流程**：页面分割 → OCR 提取文字 → 图片描述生成 → 文本合并 → 编码索引
4. **图片描述生成使用多模态 LLM（如 GPT-4V）**，可以描述图片内容、图表数据和关键标注
5. **Qdrant 支持多向量存储**，可以在同一集合中存储文本嵌入和图片嵌入，实现多模态联合检索
