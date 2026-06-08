"""断路器集成示例

展示如何将断路器集成到现有的 LLM 调用路径中。
"""

import asyncio
from typing import Any

from langchain_core.messages import HumanMessage

from app.reliability.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    circuit_breaker,
    wrap_llm_call,
    llm_circuit_breaker,
    embedding_circuit_breaker,
    reranker_circuit_breaker,
)
from app.agent.llm import create_llm


# 示例 1: 使用装饰器包装 LLM 调用
@circuit_breaker(
    failure_threshold=5,
    recovery_timeout=60,
    name="llm_invoke",
    expected_exceptions=[Exception],
)
async def invoke_llm_with_circuit_breaker(
    llm: Any,
    messages: list,
) -> str:
    """使用断路器包装的 LLM 调用"""
    response = await llm.ainvoke(messages)
    return response.content


# 示例 2: 使用上下文管理器
async def invoke_llm_with_context(
    llm: Any,
    messages: list,
) -> str:
    """使用上下文管理器的 LLM 调用"""
    async with llm_circuit_breaker.context():
        response = await llm.ainvoke(messages)
        return response.content


# 示例 3: 使用 wrap_llm_call 包装现有函数
async def invoke_llm_with_wrap(
    llm: Any,
    messages: list,
) -> str:
    """使用 wrap_llm_call 包装"""
    async def _invoke():
        response = await llm.ainvoke(messages)
        return response.content
    
    return await wrap_llm_call(_invoke, circuit_breaker=llm_circuit_breaker)


# 示例 4: 自定义断路器配置
def create_custom_circuit_breaker(
    name: str,
    failure_threshold: int = 3,
    recovery_timeout: int = 30,
) -> CircuitBreaker:
    """创建自定义断路器"""
    return CircuitBreaker(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        name=name,
        expected_exceptions=[Exception],
    )


# 示例 5: 集成到现有的 llm_invoke_with_retry 函数
async def llm_invoke_with_retry_and_circuit_breaker(
    llm: Any,
    messages: list,
    max_retries: int = 3,
    circuit_breaker: CircuitBreaker = None,
) -> str:
    """带重试和断路器的 LLM 调用"""
    if circuit_breaker is None:
        circuit_breaker = llm_circuit_breaker
    
    for attempt in range(max_retries):
        try:
            # 使用断路器检查是否可以执行
            if not await circuit_breaker.can_execute():
                raise CircuitBreakerError(
                    f"Circuit breaker '{circuit_breaker.name}' is {circuit_breaker.state.value}"
                )
            
            # 执行 LLM 调用
            response = await llm.ainvoke(messages)
            
            # 记录成功
            await circuit_breaker.record_success()
            return response.content
            
        except CircuitBreakerError:
            # 断路器打开，直接抛出
            raise
            
        except Exception as e:
            # 记录失败
            await circuit_breaker.record_failure(e)
            
            # 如果是最后一次重试，抛出异常
            if attempt == max_retries - 1:
                raise
            
            # 等待一段时间后重试
            await asyncio.sleep(2 ** attempt)
    
    raise Exception("Max retries exceeded")


# 示例 6: 批量调用时的断路器保护
async def batch_invoke_with_circuit_breaker(
    llm: Any,
    messages_list: list[list],
    circuit_breaker: CircuitBreaker = None,
) -> list[str]:
    """批量 LLM 调用，带断路器保护"""
    if circuit_breaker is None:
        circuit_breaker = llm_circuit_breaker
    
    results = []
    
    for messages in messages_list:
        try:
            result = await invoke_llm_with_circuit_breaker(llm, messages)
            results.append(result)
        except CircuitBreakerError as e:
            # 断路器打开，停止批量调用
            print(f"Circuit breaker opened: {e}")
            break
        except Exception as e:
            # 其他异常，记录但继续
            print(f"LLM call failed: {e}")
            results.append(None)
    
    return results


# 示例 7: 不同提供商使用不同的断路器
async def invoke_with_provider_circuit_breaker(
    provider: str,
    messages: list,
) -> str:
    """根据提供商使用不同的断路器"""
    # 创建提供商特定的断路器
    provider_breaker = create_custom_circuit_breaker(
        name=f"llm_{provider}",
        failure_threshold=5,
        recovery_timeout=60,
    )
    
    # 创建 LLM 实例
    llm = create_llm(model=provider)
    
    # 使用断路器包装调用
    async def _invoke():
        response = await llm.ainvoke(messages)
        return response.content
    
    return await wrap_llm_call(_invoke, circuit_breaker=provider_breaker)


# 示例 8: 监控断路器状态
async def monitor_circuit_breakers():
    """监控所有断路器状态"""
    from app.reliability.circuit_breaker import get_all_circuit_breakers
    
    breakers = get_all_circuit_breakers()
    
    for name, breaker in breakers.items():
        stats = breaker.stats
        print(f"Circuit Breaker: {name}")
        print(f"  State: {stats['state']}")
        print(f"  Failure Count: {stats['failure_count']}")
        print(f"  Total Calls: {stats['total_calls']}")
        print(f"  Total Failures: {stats['total_failures']}")
        print(f"  Total Rejected: {stats['total_rejected']}")
        print()


# 示例 9: 断路器事件回调
class CircuitBreakerWithCallback(CircuitBreaker):
    """带回调的断路器"""
    
    def __init__(self, *args, on_open=None, on_close=None, on_half_open=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.on_open = on_open
        self.on_close = on_close
        self.on_half_open = on_half_open
    
    async def record_failure(self, exception: Exception) -> None:
        """记录失败并触发回调"""
        await super().record_failure(exception)
        
        if self._state.value == "open" and self.on_open:
            self.on_open(self.name, self._failure_count)
    
    async def record_success(self) -> None:
        """记录成功并触发回调"""
        old_state = self._state
        await super().record_success()
        
        if old_state.value == "open" and self._state.value == "closed" and self.on_close:
            self.on_close(self.name)
        
        if old_state.value == "half_open" and self._state.value == "closed" and self.on_close:
            self.on_close(self.name)
    
    async def can_execute(self) -> bool:
        """检查是否可以执行并触发回调"""
        result = await super().can_execute()
        
        if self._state.value == "half_open" and self.on_half_open:
            self.on_half_open(self.name)
        
        return result


# 示例 10: 使用回调断路器
async def example_with_callback():
    """使用回调断路器示例"""
    def on_open(name, count):
        print(f"Circuit breaker '{name}' opened after {count} failures")
    
    def on_close(name):
        print(f"Circuit breaker '{name}' closed")
    
    def on_half_open(name):
        print(f"Circuit breaker '{name}' half-open")
    
    breaker = CircuitBreakerWithCallback(
        failure_threshold=3,
        recovery_timeout=10,
        name="callback_example",
        on_open=on_open,
        on_close=on_close,
        on_half_open=on_half_open,
    )
    
    # 模拟失败
    for i in range(4):
        try:
            await breaker.execute(lambda: 1/0)
        except Exception:
            pass
    
    # 等待恢复
    await asyncio.sleep(11)
    
    # 尝试执行
    try:
        await breaker.execute(lambda: "success")
    except Exception:
        pass


if __name__ == "__main__":
    # 运行示例
    asyncio.run(example_with_callback())
