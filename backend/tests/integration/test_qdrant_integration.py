"""Qdrant 集成测试 — 使用 testcontainers 启动真实 Qdrant 容器。

覆盖场景：
1. 向量索引：创建 collection、插入向量、验证计数
2. Hybrid Search：dense + sparse 向量混合检索（RRF 融合）
3. Scroll：分页遍历点
4. Payload 过滤：按 metadata 字段过滤

标记为 integration，CI 默认跳过（需安装 testcontainers 并启动 Docker）。
"""

import random
import uuid

import pytest

# testcontainers 是可选依赖，导入失败时跳过整个模块
pytest.importorskip("testcontainers")

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchValue,
    PointStruct,
    Prefetch,
    SparseIndexParams,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

# Qdrant 镜像版本（与 docker-compose.yml 保持一致）
QDRANT_IMAGE = "qdrant/qdrant:v1.12.1"
# 测试用小维度向量，加速索引和检索
DENSE_VECTOR_SIZE = 128
# 基本测试集合名（仅 dense 向量）
BASIC_COLLECTION = "test_basic_collection"
# Hybrid 测试集合名（dense + sparse 向量）
HYBRID_COLLECTION = "test_hybrid_collection"


@pytest.fixture(scope="module")
def qdrant_container():
    """启动 Qdrant 容器（模块级共享，所有测试复用同一实例）。

    使用通用 DockerContainer，兼容所有 testcontainers 版本。
    若 testcontainers 提供 QdrantContainer 也可替换为此实现。
    """
    from testcontainers.core.generic import DockerContainer
    from testcontainers.core.waiting_utils import wait_for_logs

    container = DockerContainer(QDRANT_IMAGE)
    container.with_exposed_ports(6333)
    container.start()
    # 等待 Qdrant HTTP 服务就绪
    wait_for_logs(container, "Qdrant HTTP server started", timeout=60)
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="module")
def qdrant_client(qdrant_container):
    """创建 Qdrant 客户端（模块级共享）。"""
    host = qdrant_container.get_container_host_ip()
    port = qdrant_container.get_exposed_port(6333)
    client = QdrantClient(host=host, port=int(port))
    yield client
    client.close()


@pytest.fixture(scope="module", autouse=True)
def setup_collections(qdrant_client: QdrantClient):
    """模块级 setup：创建集合并插入测试数据，测试结束后清理。

    创建两个集合：
    - BASIC_COLLECTION：仅 dense 向量，用于基础检索/过滤/分页测试
    - HYBRID_COLLECTION：dense + sparse 向量，用于 Hybrid Search 测试
    """
    client = qdrant_client

    # ── 创建基本集合（仅 dense 向量）──
    client.recreate_collection(
        collection_name=BASIC_COLLECTION,
        vectors_config=VectorParams(size=DENSE_VECTOR_SIZE, distance=Distance.COSINE),
    )

    # ── 创建 hybrid 集合（dense + sparse 向量）──
    client.recreate_collection(
        collection_name=HYBRID_COLLECTION,
        vectors_config={
            "dense": VectorParams(size=DENSE_VECTOR_SIZE, distance=Distance.COSINE),
        },
        sparse_vectors_config={
            "sparse": SparseVectorParams(index=SparseIndexParams()),
        },
    )

    # ── 插入基本测试数据（100 条 dense 向量）──
    random.seed(42)
    basic_points = []
    for i in range(100):
        vector = [random.uniform(-1, 1) for _ in range(DENSE_VECTOR_SIZE)]
        basic_points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={
                "doc_id": f"doc_{i}",
                "language": "zh" if i % 2 == 0 else "en",
                "source": "test",
                "chunk_index": i,
            },
        ))
    client.upsert(collection_name=BASIC_COLLECTION, points=basic_points)

    # ── 插入 hybrid 测试数据（50 条 dense + sparse 向量）──
    random.seed(99)
    hybrid_points = []
    for i in range(50):
        dense_vector = [random.uniform(-1, 1) for _ in range(DENSE_VECTOR_SIZE)]
        # 构造稀疏向量：每个文档有 5-10 个非零维度
        num_sparse = random.randint(5, 10)
        indices = sorted(random.sample(range(1000), num_sparse))
        values = [random.uniform(0.1, 1.0) for _ in range(num_sparse)]
        sparse_vector = SparseVector(indices=indices, values=values)
        hybrid_points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector={"dense": dense_vector, "sparse": sparse_vector},
            payload={
                "doc_id": f"hdoc_{i}",
                "category": "A" if i % 2 == 0 else "B",
            },
        ))
    client.upsert(collection_name=HYBRID_COLLECTION, points=hybrid_points)

    yield

    # ── 清理：删除集合 ──
    for name in (BASIC_COLLECTION, HYBRID_COLLECTION):
        try:
            client.delete_collection(name)
        except Exception:
            pass


@pytest.mark.integration
class TestQdrantIntegration:
    """Qdrant 集成测试套件。"""

    def test_create_collection(self, qdrant_client: QdrantClient):
        """测试创建向量集合并验证配置。"""
        info = qdrant_client.get_collection(BASIC_COLLECTION)
        assert info is not None
        # 验证向量维度配置（vectors 可能是 VectorParams 或 dict）
        vectors_config = info.config.params.vectors
        if isinstance(vectors_config, dict):
            size = vectors_config["dense"].size
        else:
            size = vectors_config.size
        assert size == DENSE_VECTOR_SIZE

    def test_insert_vectors(self, qdrant_client: QdrantClient):
        """测试插入向量并验证点计数。"""
        count = qdrant_client.count(BASIC_COLLECTION, exact=True).count
        assert count == 100

    def test_search(self, qdrant_client: QdrantClient):
        """测试向量检索（使用 query_points API）。

        qdrant-client 1.18 已移除 search 方法，统一使用 query_points。
        """
        random.seed(123)
        query_vector = [random.uniform(-1, 1) for _ in range(DENSE_VECTOR_SIZE)]

        response = qdrant_client.query_points(
            collection_name=BASIC_COLLECTION,
            query=query_vector,
            limit=10,
        )
        results = response.points
        assert len(results) == 10
        # 结果应按分数降序排列
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_payload_filter(self, qdrant_client: QdrantClient):
        """测试 Payload 过滤检索：只返回 language=zh 的文档。"""
        random.seed(456)
        query_vector = [random.uniform(-1, 1) for _ in range(DENSE_VECTOR_SIZE)]

        response = qdrant_client.query_points(
            collection_name=BASIC_COLLECTION,
            query=query_vector,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="language",
                        match=MatchValue(value="zh"),
                    ),
                ],
            ),
            limit=50,
        )
        results = response.points
        # 所有结果都应该是中文
        for r in results:
            assert r.payload["language"] == "zh"

    def test_scroll(self, qdrant_client: QdrantClient):
        """测试分页遍历所有点。"""
        all_ids = set()
        offset = None

        while True:
            points, offset = qdrant_client.scroll(
                collection_name=BASIC_COLLECTION,
                limit=20,
                offset=offset,
            )
            for p in points:
                all_ids.add(p.id)
            if offset is None:
                break

        assert len(all_ids) == 100

    def test_hybrid_search(self, qdrant_client: QdrantClient):
        """测试 Hybrid Search：dense + sparse 向量混合检索，RRF 融合。

        使用 Qdrant Query API 的 prefetch + FusionQuery(RRF)，
        与生产代码 qdrant_ops.hybrid_search_qdrant 的检索方式一致。
        """
        random.seed(789)
        dense_query = [random.uniform(-1, 1) for _ in range(DENSE_VECTOR_SIZE)]
        sparse_query = SparseVector(
            indices=[10, 50, 100, 200, 500],
            values=[0.9, 0.7, 0.5, 0.8, 0.6],
        )

        # prefetch dense + sparse，RRF 融合
        response = qdrant_client.query_points(
            collection_name=HYBRID_COLLECTION,
            prefetch=[
                Prefetch(query=dense_query, using="dense", limit=20),
                Prefetch(query=sparse_query, using="sparse", limit=20),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=5,
        )
        results = response.points
        # 应返回不超过 5 条结果，且至少有 1 条
        assert len(results) <= 5
        assert len(results) > 0
        # 验证每个结果有分数
        for r in results:
            assert r.score is not None

    def test_hybrid_search_with_filter(self, qdrant_client: QdrantClient):
        """测试带 Payload 过滤的 Hybrid Search：只返回 category=A 的文档。"""
        random.seed(321)
        dense_query = [random.uniform(-1, 1) for _ in range(DENSE_VECTOR_SIZE)]
        sparse_query = SparseVector(
            indices=[5, 15, 25],
            values=[0.8, 0.6, 0.9],
        )

        response = qdrant_client.query_points(
            collection_name=HYBRID_COLLECTION,
            prefetch=[
                Prefetch(query=dense_query, using="dense", limit=20),
                Prefetch(query=sparse_query, using="sparse", limit=20),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="category",
                        match=MatchValue(value="A"),
                    ),
                ],
            ),
            limit=10,
        )
        results = response.points
        # 所有结果都应该是 category A
        for r in results:
            assert r.payload["category"] == "A"

    def test_delete_collection(self, qdrant_client: QdrantClient):
        """测试删除集合：删除后获取应抛异常。

        使用独立的临时集合，不影响其他测试。
        """
        temp_name = "test_temp_delete_collection"
        # 创建临时集合
        qdrant_client.recreate_collection(
            collection_name=temp_name,
            vectors_config=VectorParams(size=DENSE_VECTOR_SIZE, distance=Distance.COSINE),
        )
        # 确认集合存在
        assert qdrant_client.get_collection(temp_name) is not None

        # 删除集合
        qdrant_client.delete_collection(temp_name)
        # 删除后获取应抛异常
        with pytest.raises(Exception):
            qdrant_client.get_collection(temp_name)
