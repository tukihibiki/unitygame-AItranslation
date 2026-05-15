from urllib.parse import parse_qs


def parse_custom_translate(body: bytes, content_type: str) -> str | None:
    """Parse XUnity.AutoTranslator CustomTranslate request body.

    Supports three formats:
      1. text/plain           -> body is the raw Japanese text
      2. application/x-www-form-urlencoded -> body contains "text=" or "q=" param
      3. application/json     -> body contains {"text": "..."}

    Returns the extracted text or None if unparseable.
    """
    if not body:
        return None

    ct = (content_type or "").split(";")[0].strip().lower()

    if ct == "text/plain":
        return body.decode("utf-8", errors="replace").strip()

    if ct == "application/x-www-form-urlencoded":
        params = parse_qs(body.decode("utf-8", errors="replace"))
        for key in ("text", "q", "source_text", "sentence"):
            if key in params:
                return params[key][0]
        return None

    if ct == "application/json":
        import json
        try:
            data = json.loads(body)
            return data.get("text", data.get("q", data.get("sentence", None)))
        except (json.JSONDecodeError, TypeError):
            return None

    # Fallback: try to decode as plain text anyway
    try:
        text = body.decode("utf-8", errors="replace").strip()
        if text:
            return text
    except Exception:
        return None

    return None
