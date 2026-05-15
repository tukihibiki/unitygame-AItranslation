import aiohttp
import asyncio
import logging
import time
import re
from .llm_prompts import build_messages

logger = logging.getLogger(__name__)

THINK_STRIP = re.compile(r"<think>.*?</think>", re.DOTALL)
THINK_STRIP_GREEDY = re.compile(r"<think>.*", re.DOTALL)


class OllamaClient:
    """Local LLM via Ollama — fast (<500ms) but less accurate."""

    def __init__(self, config: dict):
        self._base_url = config.get("base_url", "http://127.0.0.1:11434")
        self._model = config.get("model", "qwen3:0.6b")
        self._timeout = config.get("timeout", 10)
        self._session: aiohttp.ClientSession | None = None

    @property
    def model(self) -> str:
        return f"ollama:{self._model}"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def translate(self, text: str) -> str | None:
        """Translate text. Returns None if Ollama is unavailable."""
        num_predict = max(200, min(800, 300 + len(text) * 2))
        try:
            session = await self._get_session()
            url = f"{self._base_url}/api/generate"
            prompt = f"Translate Japanese to Simplified Chinese. Output ONLY the Chinese translation.\n\n{text}"
            payload = {
                "model": self._model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0, "num_predict": num_predict},
            }
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                raw = data.get("response", "")
                # Strip <think>...</think> if present
                clean = THINK_STRIP.sub("", raw).strip()
                # If think block wasn't closed (truncated), strip everything from <think>
                if clean.startswith("<think>"):
                    clean = THINK_STRIP_GREEDY.sub("", clean).strip()
                if not clean:
                    return None
                return clean
        except (asyncio.TimeoutError, aiohttp.ClientError, Exception) as e:
            logger.debug(f"Ollama unavailable: {e}")
            return None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


class CloudLLMClient:
    """Cloud LLM API — slower (~1s) but more accurate translation."""

    def __init__(self, config: dict):
        self._api_key = config["api_key"]
        self._base_url = config["base_url"]
        self._model = config["model"]
        self._temperature = config.get("temperature", 0.1)
        self._max_tokens = config.get("max_tokens", 200)
        self._timeout = config.get("timeout", 15)
        self._max_retries = config.get("max_retries", 2)
        self._session: aiohttp.ClientSession | None = None
        self._total_cost = 0.0
        self._total_tokens = 0

    @property
    def model(self) -> str:
        return self._model

    @property
    def total_cost(self) -> float:
        return self._total_cost

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=8, ttl_dns_cache=300, keepalive_timeout=60)
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            self._session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        return self._session

    async def translate(self, text: str) -> str:
        if not self._api_key:
            return "[错误: 未设置API Key]"

        messages = build_messages(text)
        url = f"{self._base_url}/chat/completions"

        last_error = None
        for attempt in range(self._max_retries + 1):
            try:
                session = await self._get_session()
                headers = {
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": self._model,
                    "messages": messages,
                    "temperature": self._temperature,
                    "max_tokens": self._max_tokens,
                }
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return self._parse_response(data)
                    if resp.status == 429:
                        retry_after = resp.headers.get("Retry-After", "3")
                        wait = int(retry_after) if retry_after.isdigit() else 3
                        logger.warning(f"Rate limited, waiting {wait}s")
                        await asyncio.sleep(wait)
                        continue
                    if resp.status >= 500:
                        last_error = f"Server error {resp.status}"
                        if attempt < self._max_retries:
                            wait = min(2**attempt, 8)
                            logger.warning(f"{last_error}, retry {attempt + 1}/{self._max_retries} in {wait}s")
                            await asyncio.sleep(wait)
                            continue
                        return f"[翻译失败: {last_error}]"
                    body = await resp.text()
                    logger.error(f"API error {resp.status}: {body[:200]}")
                    return f"[翻译失败: HTTP {resp.status}]"

            except asyncio.TimeoutError:
                last_error = "超时"
                if attempt < self._max_retries:
                    logger.warning(f"API timeout, retry {attempt + 1}/{self._max_retries}")
                    continue
                return "[翻译超时]"
            except aiohttp.ClientError as e:
                last_error = str(e)
                if attempt < self._max_retries:
                    logger.warning(f"Connection error: {e}, retry {attempt + 1}")
                    await asyncio.sleep(1)
                    continue
                return f"[网络错误: {last_error[:50]}]"

        return f"[翻译失败: {last_error}]"

    def _parse_response(self, data: dict) -> str:
        try:
            content = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            self._total_tokens += prompt_tokens + completion_tokens
            cost = (prompt_tokens / 1_000_000) * 0.14 + (completion_tokens / 1_000_000) * 0.28
            self._total_cost += cost
            return content
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Failed to parse API response: {e}")
            return "[解析响应失败]"

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


class HybridLLMClient:
    """Local-first translation: Ollama → fallback to Cloud."""

    def __init__(self, config: dict):
        ollama_config = config.get("ollama", {})
        cloud_config = config.get("llm", {})
        self._ollama_enabled = ollama_config.get("enabled", True) if isinstance(ollama_config, dict) else bool(ollama_config)
        self._cloud_enabled = cloud_config.get("enabled", True) if isinstance(cloud_config, dict) else True
        self._ollama = OllamaClient(ollama_config) if self._ollama_enabled else None
        self._cloud = CloudLLMClient(cloud_config) if self._cloud_enabled else None
        self._local_hits = 0
        self._cloud_hits = 0

    @property
    def total_cost(self) -> float:
        return self._cloud.total_cost

    @property
    def total_tokens(self) -> int:
        return self._cloud.total_tokens

    @property
    def stats(self) -> dict:
        return {"local_hits": self._local_hits, "cloud_hits": self._cloud_hits}

    async def translate(self, text: str) -> str:
        # Try Ollama local model first (if enabled)
        if self._ollama is not None:
            t0 = time.time()
            local_result = await self._ollama.translate(text)
            if local_result:
                self._local_hits += 1
                logger.info(f"Local: {(time.time() - t0) * 1000:.0f}ms [{text[:30]}...]")
                return local_result

        # Fall back to cloud API (if enabled)
        if self._cloud is not None:
            if self._ollama is not None:
                logger.info(f"Falling back to cloud for: {text[:40]}...")
            cloud_result = await self._cloud.translate(text)
            self._cloud_hits += 1
            return cloud_result

        # Both disabled — return original text
        return text

    async def close(self):
        if self._ollama is not None:
            await self._ollama.close()
        if self._cloud is not None:
            await self._cloud.close()
