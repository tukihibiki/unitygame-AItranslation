#!/usr/bin/env python3
"""Hanhua — Unity Mono Game Japanese-to-Chinese LLM Translation Server."""

import logging
import sys
import os
import json

from aiohttp import web

from .config import load_config
from .protocols import parse_custom_translate
from .translation_pipeline import TranslationPipeline

logger = logging.getLogger(__name__)
_pipeline: TranslationPipeline | None = None


async def handle_translate(request: web.Request) -> web.Response:
    body = await request.read()
    content_type = request.content_type or "text/plain"
    text = parse_custom_translate(body, content_type)
    if text is None:
        return web.Response(text="", status=400)
    logger.info(f"Received: '{text[:80]}{'...' if len(text) > 80 else ''}'")
    translated = await _pipeline.translate(text)
    logger.info(f"Translated: '{translated[:80]}{'...' if len(translated) > 80 else ''}'")
    return web.Response(text=translated, content_type="text/plain", charset="utf-8")


async def handle_stats(request: web.Request) -> web.Response:
    stats = _pipeline.stats if _pipeline else {}
    return web.Response(text=json.dumps(stats, ensure_ascii=False, indent=2),
                        content_type="application/json", charset="utf-8")


async def handle_history(request: web.Request) -> web.Response:
    """GET /history?limit=50 — Recent translation history."""
    limit = int(request.query.get("limit", 50))
    if _pipeline:
        import sqlite3, time
        rows = []
        try:
            conn = _pipeline._cache._get_conn()
            cur = conn.execute(
                "SELECT source_text, translated_text, model, duration_ms, last_accessed_at "
                "FROM translations ORDER BY last_accessed_at DESC LIMIT ?",
                (limit,)
            )
            for src, tgt, model, dur, ts in cur.fetchall():
                rows.append({
                    "source": src[:100],
                    "target": tgt[:100],
                    "model": model,
                    "duration_ms": round(dur, 1),
                    "time": time.strftime("%H:%M:%S", time.localtime(ts)),
                })
        except Exception:
            pass
        return web.Response(text=json.dumps(rows, ensure_ascii=False),
                            content_type="application/json", charset="utf-8")
    return web.Response(text="[]", content_type="application/json", charset="utf-8")


async def handle_health(request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def on_startup(app: web.Application):
    global _pipeline
    config = load_config()
    _pipeline = TranslationPipeline(config)
    logger.info(f"Hanhua server started on {config['server']['host']}:{config['server']['port']}")
    logger.info(f"LLM: {config['llm']['provider']}/{config['llm']['model']}")
    ollama = config.get("ollama", {})
    if ollama.get("enabled", True):
        logger.info(f"Local: Ollama {ollama.get('model', 'qwen3:0.6b')} (adaptive tokens)")


async def on_shutdown(app: web.Application):
    global _pipeline
    if _pipeline:
        await _pipeline.shutdown()
    logger.info("Hanhua server stopped")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    config = load_config()
    host = config["server"]["host"]
    port = config["server"]["port"]

    app = web.Application()
    app.router.add_post("/", handle_translate)
    app.router.add_get("/", handle_health)
    app.router.add_get("/stats", handle_stats)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/history", handle_history)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    web.run_app(app, host=host, port=port, print=lambda *a, **kw: None)


if __name__ == "__main__":
    main()
