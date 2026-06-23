"""TaskGroup 迁移后的行为测试。

验证 R7 改造：asyncio.gather → asyncio.TaskGroup 的正确性。
重点测试：
1. TaskGroup 结果顺序保持（indexer.py 上下文前缀生成所依赖的模式）
2. TaskGroup 错误传播（任一失败取消其他）
3. 实际迁移函数 _generate_context_prefixes_async 的行为
"""

import asyncio

import pytest

from app.rag.indexer import _generate_context_prefixes_async


async def test_taskgroup_preserves_result_order() -> None:
    """TaskGroup 按任务创建顺序返回结果（indexer.py 第 177 行迁移所依赖的模式）。"""
    async def make(value: int) -> int:
        # 引入随机延迟打乱完成顺序，验证结果仍按创建顺序
        await asyncio.sleep(0.01 * (10 - value))
        return value

    coros = [make(i) for i in range(5)]
    task_refs: list[asyncio.Task[int]] = []
    async with asyncio.TaskGroup() as tg:
        for c in coros:
            task_refs.append(tg.create_task(c))

    results = [t.result() for t in task_refs]
    assert results == [0, 1, 2, 3, 4]


async def test_taskgroup_propagates_error() -> None:
    """TaskGroup 任一任务失败时抛出异常（错误传播优于 gather）。"""
    async def succeed() -> str:
        await asyncio.sleep(0.05)
        return "ok"

    async def fail() -> str:
        await asyncio.sleep(0.01)
        raise ValueError("任务失败")

    task_refs: list[asyncio.Task] = []
    with pytest.raises(ExceptionGroup):  # noqa: PT012
        async with asyncio.TaskGroup() as tg:
            task_refs.append(tg.create_task(succeed()))
            task_refs.append(tg.create_task(fail()))


async def test_taskgroup_empty_tasks_returns_empty() -> None:
    """空任务列表时 TaskGroup 正常完成，结果为空（边界情况）。"""
    task_refs: list[asyncio.Task] = []
    async with asyncio.TaskGroup():
        pass  # 无任务

    results = [t.result() for t in task_refs]
    assert results == []


async def test_generate_context_prefixes_async_basic() -> None:
    """迁移后的 _generate_context_prefixes_async 正常生成上下文前缀。"""
    def mock_llm_call(messages: list) -> str:
        # 模拟 LLM 返回上下文前缀
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        return "生成的上下文前缀"

    chunks_with_docs = [
        ("chunk 文本 1", "文档全文 1"),
        ("chunk 文本 2", "文档全文 2"),
        ("chunk 文本 3", "文档全文 3"),
    ]

    results = await _generate_context_prefixes_async(chunks_with_docs, mock_llm_call)

    assert len(results) == 3
    assert all(r == "生成的上下文前缀" for r in results)


async def test_generate_context_prefixes_async_preserves_order() -> None:
    """迁移后结果顺序与输入顺序一致（TaskGroup 按创建顺序提取结果）。"""
    def mock_llm_call(messages: list) -> str:
        # 从 prompt 中提取 chunk 文本作为返回，验证顺序
        content = messages[0]["content"]
        # chunk 文本在 <chunk> 标签内
        start = content.index("<chunk>") + len("<chunk>")
        end = content.index("</chunk>")
        return content[start:end].strip()

    chunks_with_docs = [
        ("第一段", "文档 A"),
        ("第二段", "文档 B"),
        ("第三段", "文档 C"),
    ]

    results = await _generate_context_prefixes_async(chunks_with_docs, mock_llm_call)

    assert results == ["第一段", "第二段", "第三段"]


async def test_generate_context_prefixes_async_empty_input() -> None:
    """空输入返回空列表（TaskGroup 无任务的边界情况）。"""
    def mock_llm_call(messages: list) -> str:
        return ""

    results = await _generate_context_prefixes_async([], mock_llm_call)
    assert results == []


async def test_generate_context_prefixes_async_non_string_result() -> None:
    """LLM 返回非字符串时自动转为字符串（兼容性处理）。"""
    def mock_llm_call(messages: list) -> dict:
        return {"text": "非字符串结果"}

    chunks_with_docs = [("chunk", "doc")]
    results = await _generate_context_prefixes_async(chunks_with_docs, mock_llm_call)

    assert len(results) == 1
    assert isinstance(results[0], str)
    assert "非字符串结果" in results[0]


async def test_generate_context_prefixes_async_concurrency_limit() -> None:
    """并发数受 max_concurrent 信号量限制。"""
    current_concurrent = 0
    max_observed_concurrent = 0

    def mock_llm_call(messages: list) -> str:
        nonlocal current_concurrent, max_observed_concurrent
        current_concurrent += 1
        max_observed_concurrent = max(max_observed_concurrent, current_concurrent)
        # 模拟耗时，让多个任务有机会并发
        import time
        time.sleep(0.02)
        current_concurrent -= 1
        return "prefix"

    # 10 个 chunk，限制并发为 3
    chunks_with_docs = [(f"chunk-{i}", f"doc-{i}") for i in range(10)]
    await _generate_context_prefixes_async(chunks_with_docs, mock_llm_call, max_concurrent=3)

    # 观察到的最大并发数不应超过限制
    assert max_observed_concurrent <= 3
    assert max_observed_concurrent >= 1


async def test_hybrid_retrieve_taskgroup_pattern_two_tasks() -> None:
    """验证 hybrid_retrieve_async 使用的双任务 TaskGroup 模式（indexer.py 第 400 行）。"""
    async def bm25_like() -> list[str]:
        await asyncio.sleep(0.01)
        return ["bm25-result"]

    async def vector_like() -> list[str]:
        await asyncio.sleep(0.01)
        return ["vector-result"]

    task_refs: list[asyncio.Task] = []
    async with asyncio.TaskGroup() as tg:
        task_refs.append(tg.create_task(bm25_like()))
        task_refs.append(tg.create_task(vector_like()))

    bm25_results = task_refs[0].result()
    vector_results = task_refs[1].result()

    assert bm25_results == ["bm25-result"]
    assert vector_results == ["vector-result"]
