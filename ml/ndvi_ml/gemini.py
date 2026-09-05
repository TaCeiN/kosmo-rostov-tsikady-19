"""Тонкий клиент Gemini: держит ключ на сервере и ходит в REST напрямую.

Ключ живёт только здесь. Отдавать его браузеру нельзя — из devtools его
заберёт кто угодно, а платит за запросы владелец проекта. Поэтому фронт зовёт
наши /ai/*, а наружу выходит уже бэкенд.

    GEMINI_API_KEY=...      обязателен, без него ИИ-функции просто выключены
    GEMINI_MODEL=...        по умолчанию gemini-2.5-flash

SDK намеренно не тянем: один POST с JSON закрывает всю задачу, а лишняя
зависимость в requirements ломала бы уже собранные окружения.
"""
from __future__ import annotations

import os

import httpx

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.5-flash"

# Генерация текста упирается не в сеть, а в саму модель: длинный разбор
# поля она пишет десятки секунд.
TIMEOUT_S = 90.0


class GeminiError(RuntimeError):
    """Ошибка обращения к Gemini, пригодная для показа пользователю."""


def api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def model_name() -> str:
    return os.environ.get("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def available() -> bool:
    """Есть ли ключ. Фронт прячет ИИ-панель, если нет."""
    return bool(api_key())


def _extract_text(payload: dict) -> str:
    """Достаёт текст ответа, разбирая причины пустого результата.

    Пустой candidates при HTTP 200 — обычное дело: сработал фильтр
    безопасности или кончился лимит токенов. Молча вернуть '' нельзя,
    иначе в интерфейсе появится пустая карточка без объяснений.
    """
    candidates = payload.get("candidates") or []

    if not candidates:
        block = (payload.get("promptFeedback") or {}).get("blockReason")
        raise GeminiError(
            f"модель не дала ответ (блокировка: {block})" if block
            else "модель вернула пустой ответ"
        )

    first = candidates[0]
    parts = (first.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()

    if not text:
        reason = first.get("finishReason")
        if reason == "MAX_TOKENS":
            raise GeminiError("ответ не поместился в лимит токенов")
        raise GeminiError(f"пустой ответ модели (finishReason: {reason})")

    return text


def _post(body: dict, key: str) -> httpx.Response:
    url = f"{API_ROOT}/{model_name()}:generateContent"
    try:
        return httpx.post(
            url,
            json=body,
            # Ключ заголовком, а не в query: URL светится в логах и трейсах
            headers={"x-goog-api-key": key},
            timeout=TIMEOUT_S,
        )
    except httpx.TimeoutException as exc:
        raise GeminiError(f"модель не ответила за {int(TIMEOUT_S)} с") from exc
    except httpx.HTTPError as exc:
        raise GeminiError(f"сеть до Gemini недоступна: {exc}") from exc


def generate(prompt: str, system: str | None = None,
             temperature: float = 0.4, max_tokens: int = 4096) -> str:
    """Один запрос к модели. Бросает GeminiError с человекочитаемой причиной."""
    key = api_key()
    if not key:
        raise GeminiError("GEMINI_API_KEY не задан: ИИ-функции выключены")

    body: dict = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            # У 2.5-flash размышления тратят тот же бюджет, что и ответ:
            # с включёнными разбор поля обрывался на середине по MAX_TOKENS.
            # Задача здесь — прочитать готовые числа, думать вслух незачем.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    resp = _post(body, key)

    # Модель без поддержки thinkingConfig отвечает 400: повторяем без него,
    # чтобы смена GEMINI_MODEL на другую версию не ломала ИИ-функции целиком
    if resp.status_code == 400 and "thinking" in resp.text.lower():
        body["generationConfig"].pop("thinkingConfig", None)
        resp = _post(body, key)

    if resp.status_code != 200:
        detail = ""
        try:
            detail = (resp.json().get("error") or {}).get("message", "")
        except Exception:
            detail = resp.text[:300]
        raise GeminiError(f"Gemini ответил {resp.status_code}: {detail}")

    return _extract_text(resp.json())
