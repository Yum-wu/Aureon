"""��·������ʾ��

չʾ��ν���·�����ɵ����е� LLM ����·���С�
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


# ʾ�� 1: ʹ��װ������װ LLM ����
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
    """ʹ�ö�·����װ�� LLM ����"""
    response = await llm.ainvoke(messages)
    return response.content


# ʾ�� 2: ʹ�������Ĺ�����
async def invoke_llm_with_context(
    llm: Any,
    messages: list,
) -> str:
    """ʹ�������Ĺ������� LLM ����"""
    async with llm_circuit_breaker.context():
        response = await llm.ainvoke(messages)
        return response.content


# ʾ�� 3: ʹ�� wrap_llm_call ��װ���к���
async def invoke_llm_with_wrap(
    llm: Any,
    messages: list,
) -> str:
    """ʹ�� wrap_llm_call ��װ"""
    async def _invoke():
        response = await llm.ainvoke(messages)
        return response.content
    
    return await wrap_llm_call(_invoke, circuit_breaker=llm_circuit_breaker)


# ʾ�� 4: �Զ����·������
def create_custom_circuit_breaker(
    name: str,
    failure_threshold: int = 3,
    recovery_timeout: int = 30,
) -> CircuitBreaker:
    """�����Զ����·��"""
    return CircuitBreaker(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        name=name,
        expected_exceptions=[Exception],
    )


# ʾ�� 5: ���ɵ����е� llm_invoke_with_retry ����
async def llm_invoke_with_retry_and_circuit_breaker(
    llm: Any,
    messages: list,
    max_retries: int = 3,
    circuit_breaker: CircuitBreaker = None,
) -> str:
    """�����ԺͶ�·���� LLM ����"""
    if circuit_breaker is None:
        circuit_breaker = llm_circuit_breaker
    
    for attempt in range(max_retries):
        try:
            # ʹ�ö�·������Ƿ����ִ��
            if not await circuit_breaker.can_execute():
                raise CircuitBreakerError(
                    f"Circuit breaker '{circuit_breaker.name}' is {circuit_breaker.state.value}"
                )
            
            # ִ�� LLM ����
            response = await llm.ainvoke(messages)
            
            # ��¼�ɹ�
            await circuit_breaker.record_success()
            return response.content
            
        except CircuitBreakerError:
            # ��·���򿪣�ֱ���׳�
            raise
            
        except Exception as e:
            # ��¼ʧ��
            await circuit_breaker.record_failure(e)
            
            # ��������һ�����ԣ��׳��쳣
            if attempt == max_retries - 1:
                raise
            
            # �ȴ�һ��ʱ�������
            await asyncio.sleep(2 ** attempt)
    
    raise Exception("Max retries exceeded")


# ʾ�� 6: ��������ʱ�Ķ�·������
async def batch_invoke_with_circuit_breaker(
    llm: Any,
    messages_list: list[list],
    circuit_breaker: CircuitBreaker = None,
) -> list[str]:
    """���� LLM ���ã�����·������"""
    if circuit_breaker is None:
        circuit_breaker = llm_circuit_breaker
    
    results = []
    
    for messages in messages_list:
        try:
            result = await invoke_llm_with_circuit_breaker(llm, messages)
            results.append(result)
        except CircuitBreakerError as e:
            # ��·���򿪣�ֹͣ��������
            print(f"Circuit breaker opened: {e}")
            break
        except Exception as e:
            # �����쳣����¼������
            print(f"LLM call failed: {e}")
            results.append(None)
    
    return results


# ʾ�� 7: ��ͬ�ṩ��ʹ�ò�ͬ�Ķ�·��
async def invoke_with_provider_circuit_breaker(
    provider: str,
    messages: list,
) -> str:
    """�����ṩ��ʹ�ò�ͬ�Ķ�·��"""
    # �����ṩ���ض��Ķ�·��
    provider_breaker = create_custom_circuit_breaker(
        name=f"llm_{provider}",
        failure_threshold=5,
        recovery_timeout=60,
    )
    
    # ���� LLM ʵ��
    llm = create_llm(model=provider)
    
    # ʹ�ö�·����װ����
    async def _invoke():
        response = await llm.ainvoke(messages)
        return response.content
    
    return await wrap_llm_call(_invoke, circuit_breaker=provider_breaker)


# ʾ�� 8: ��ض�·��״̬
async def monitor_circuit_breakers():
    """������ж�·��״̬"""
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


# ʾ�� 9: ��·���¼��ص�
class CircuitBreakerWithCallback(CircuitBreaker):
    """���ص��Ķ�·��"""
    
    def __init__(self, *args, on_open=None, on_close=None, on_half_open=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.on_open = on_open
        self.on_close = on_close
        self.on_half_open = on_half_open
    
    async def record_failure(self, exception: Exception) -> None:
        """��¼ʧ�ܲ������ص�"""
        await super().record_failure(exception)
        
        if self._state.value == "open" and self.on_open:
            self.on_open(self.name, self._failure_count)
    
    async def record_success(self) -> None:
        """��¼�ɹ��������ص�"""
        old_state = self._state
        await super().record_success()
        
        if old_state.value == "open" and self._state.value == "closed" and self.on_close:
            self.on_close(self.name)
        
        if old_state.value == "half_open" and self._state.value == "closed" and self.on_close:
            self.on_close(self.name)
    
    async def can_execute(self) -> bool:
        """����Ƿ����ִ�в������ص�"""
        result = await super().can_execute()
        
        if self._state.value == "half_open" and self.on_half_open:
            self.on_half_open(self.name)
        
        return result


# ʾ�� 10: ʹ�ûص���·��
async def example_with_callback():
    """ʹ�ûص���·��ʾ��"""
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
    
    # ģ��ʧ��
    for i in range(4):
        try:
            await breaker.execute(lambda: 1/0)
        except Exception:
            pass
    
    # �ȴ��ָ�
    await asyncio.sleep(11)
    
    # ����ִ��
    try:
        await breaker.execute(lambda: "success")
    except Exception:
        pass


if __name__ == "__main__":
    # ����ʾ��
    asyncio.run(example_with_callback())
