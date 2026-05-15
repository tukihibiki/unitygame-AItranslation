import logging
import time
from .debounce import DebounceQueue
from .language_detect import is_japanese, is_chinese
from .cache import TranslationCache
from .llm_client import HybridLLMClient

logger = logging.getLogger(__name__)


class TranslationPipeline:
    def __init__(self, config: dict):
        self._config = config
        self._cache = TranslationCache(
            db_path=config["cache"]["db_path"],
            max_entries=config["cache"]["max_entries"],
        )
        self._llm = HybridLLMClient(config)
        self._model_path = config["language"]["model_path"]
        self._min_confidence = config["language"]["min_confidence"]
        self._debounce = DebounceQueue(
            window_ms=config["debounce"]["window_ms"],
            immediate_on_punctuation=config["debounce"]["immediate_on_punctuation"],
        )
        self._debounce.set_handler(self._on_debounced)

        self._stats = {"requests": 0, "cache_hits": 0, "skipped": 0, "translated": 0}

    @property
    def stats(self) -> dict:
        cache_stats = self._cache.stats()
        llm_stats = self._llm.stats
        return {
            **self._stats,
            "cache_entries": cache_stats["entries"],
            "cache_total_hits": cache_stats["total_hits"],
            "llm_tokens": self._llm.total_tokens,
            "llm_cost": round(self._llm.total_cost, 6),
            "local_hits": llm_stats.get("local_hits", 0),
            "cloud_hits": llm_stats.get("cloud_hits", 0),
        }

    async def translate(self, text: str) -> str:
        """Main entry: receive raw text, return translated text."""
        if not text or not text.strip():
            return text

        text = text.strip()
        self._stats["requests"] += 1

        # Stage 1: Cache lookup
        cached = self._cache.lookup(text)
        if cached is not None:
            self._stats["cache_hits"] += 1
            return cached

        # Stage 2: Language gate — already Chinese, return as-is
        if is_chinese(text, self._model_path, self._min_confidence):
            self._stats["skipped"] += 1
            self._cache.store(text, text, model="identity")
            return text

        # Stage 3: Language gate — not Japanese, skip
        if not is_japanese(text, self._model_path, self._min_confidence):
            self._stats["skipped"] += 1
            logger.debug(f"Skipped non-Japanese text: '{text[:60]}...'")
            return text

        # Stage 4: LLM translation
        t0 = time.time()
        result = await self._llm.translate(text)
        duration_ms = (time.time() - t0) * 1000
        self._stats["translated"] += 1

        if result and not result.startswith("["):
            self._cache.store(text, result, model="hybrid", duration_ms=duration_ms)

        return result

    async def _on_debounced(self, text: str):
        """Called when debounce settles. Used for the batch/debounced path."""
        # This is the debounced pipeline entry — for future async overlay integration
        pass

    async def shutdown(self):
        await self._debounce.shutdown()
        self._cache.close()
