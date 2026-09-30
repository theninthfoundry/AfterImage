import json, os
import httpx


class LLMError(Exception):
    pass


def lesson(inc: dict, tested: list[dict], draft: str) -> str:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise LLMError("GROQ_API_KEY not set")
    body = {"model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"), "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": 'Write one operational lesson for an incident memory using only the facts given. Reply as JSON: {"lesson": "<max 280 chars>"}'},
                         {"role": "user", "content": json.dumps({"incident": inc["id"], "service": inc["service"], "root_cause": inc["root"], "tested": tested, "draft": draft})}]}
    try:
        r = httpx.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=body, timeout=20)
        r.raise_for_status()
        text = json.loads(r.json()["choices"][0]["message"]["content"])["lesson"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as e:
        raise LLMError(type(e).__name__) from e
    if not isinstance(text, str) or not 10 <= len(text) <= 280:
        raise LLMError("invalid lesson")
    return text
