import hashlib
import asyncio
import time
import logging

logger = logging.getLogger(__name__)

SENTENCE_END = set("。！？!?…~.）\)」』》】")


class DebounceQueue:
    """Trailing-edge debounce: only emits text after it has been stable for `window_ms`.

    If the text ends with sentence-ending punctuation and immediate_on_punctuation
    is True, the text is emitted immediately without waiting.
    """

    def __init__(self, window_ms: int = 500, immediate_on_punctuation: bool = True):
        self._window_ms = window_ms
        self._immediate = immediate_on_punctuation
        self._timers: dict[str, asyncio.Task] = {}
        self._ring: list[str] = []
        self._ring_max = 64
        self._on_emit: callable | None = None

    def set_handler(self, handler: callable):
        self._on_emit = handler

    def _hash(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def _ends_with_punctuation(self, text: str) -> bool:
        if not text:
            return False
        return text.strip()[-1] in SENTENCE_END

    async def push(self, text: str) -> None:
        if not text or not text.strip():
            return

        text = text.strip()
        h = self._hash(text)

        # Ring buffer dedup: skip identical text that arrived recently
        if h in self._ring:
            return
        self._ring.append(h)
        if len(self._ring) > self._ring_max:
            self._ring.pop(0)

        # Immediate send on sentence-ending punctuation
        if self._immediate and self._ends_with_punctuation(text):
            if h in self._timers:
                self._timers[h].cancel()
                del self._timers[h]
            await self._emit(text)
            return

        # Start / reset debounce timer for this hash
        if h in self._timers:
            self._timers[h].cancel()

        self._timers[h] = asyncio.create_task(self._debounce_timer(text, h))

    async def _debounce_timer(self, text: str, h: str):
        try:
            await asyncio.sleep(self._window_ms / 1000.0)
            del self._timers[h]
            await self._emit(text)
        except asyncio.CancelledError:
            pass

    async def _emit(self, text: str):
        if self._on_emit:
            try:
                await self._on_emit(text)
            except Exception as e:
                logger.error(f"Debounce emit handler error: {e}")

    async def shutdown(self):
        for h, task in list(self._timers.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._timers.clear()
