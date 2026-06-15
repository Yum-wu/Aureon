"""CrossEncoder safety patch �� prevents OOM on constrained environments.



Must be imported BEFORE any sentence_transformers usage.

When RERANK_ENABLED=false, replaces CrossEncoder with a stub that raises

RuntimeError on instantiation, preventing the model from loading into memory.

"""



from app.config import settings as _cfg



_rerank_disabled = not _cfg.rerank.rerank_enabled



if _rerank_disabled:

    try:

        import sentence_transformers as _st



        _OrigCE = _st.CrossEncoder



        class _DisabledCrossEncoder:

            """Stub that prevents CrossEncoder from loading (avoids OOM on Railway)."""



            def __init__(self, *args, **kwargs):

                raise RuntimeError(

                    "CrossEncoder disabled (RERANK_ENABLED=false). "

                    "Set RERANK_ENABLED=true or increase memory to enable reranking."

                )



            def __getattr__(self, name):

                raise RuntimeError("CrossEncoder disabled (RERANK_ENABLED=false)")



        _st.CrossEncoder = _DisabledCrossEncoder



        import structlog

        structlog.get_logger().info("CrossEncoder disabled via RERANK_ENABLED=false")

    except ImportError:

        pass  # sentence-transformers not installed, nothing to patch

