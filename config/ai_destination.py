"""Canonical AI destinations, shared by transport and credential storage."""

from urllib.parse import urlsplit, urlunsplit

DEFAULT_MODELS = {
    "openai": "gpt-6.1-sol",
    "anthropic": "claude-sonnet-4-20250514",
    "google": "gemini-2.0-flash",
    "deepseek": "deepseek-chat",
}
API_ENDPOINTS = {
    "openai": "https://api.openai.com/v1/responses",
    "anthropic": "https://api.anthropic.com/v1/messages",
    "google": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
}


def destination(provider, endpoint="", protocol="auto"):
    if provider not in (*API_ENDPOINTS, "compatible", ""):
        raise ValueError("Provedor não suportado")
    if protocol not in ("auto", "responses", "chat_completions"):
        raise ValueError("Protocolo não suportado")
    endpoint = (endpoint or "").strip().rstrip("/")
    if not endpoint:
        if provider == "compatible":
            raise ValueError("Informe a URL-base do servidor compatível")
        if provider == "openai":
            return (
                ("https://api.openai.com/v1/chat/completions", "chat_completions")
                if protocol == "chat_completions"
                else (API_ENDPOINTS[provider], "responses")
            )
        return API_ENDPOINTS.get(
            provider, ""
        ), "chat_completions" if provider == "deepseek" else provider
    u = urlsplit(endpoint)
    if (
        u.scheme not in ("http", "https")
        or not u.hostname
        or u.username
        or u.password
        or u.query
        or u.fragment
    ):
        raise ValueError("Endpoint inválido: use URL sem credenciais, query ou fragmento")
    if u.scheme == "http" and u.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("HTTP permitido somente para modelos locais")
    if not provider:
        raise ValueError("Selecione um provedor")
    inferred = (
        "responses"
        if u.path.endswith("/responses")
        else "chat_completions"
        if u.path.endswith("/chat/completions")
        else None
    )
    if inferred and protocol != "auto" and inferred != protocol:
        raise ValueError("O endpoint completo e o protocolo selecionado são diferentes")
    selected = inferred or (
        "responses"
        if protocol == "responses"
        or (protocol == "auto" and provider == "openai" and endpoint == "https://api.openai.com/v1")
        else "chat_completions"
    )
    if not inferred:
        endpoint += "/responses" if selected == "responses" else "/chat/completions"
    return endpoint, selected


def credential_scope(llm):
    """Protocols on the same base destination share credentials, hosts never do."""
    url, _ = destination(
        llm.provider, getattr(llm, "endpoint", ""), getattr(llm, "protocol", "auto")
    )
    for suffix in ("/chat/completions", "/responses"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
            break
    u = urlsplit(url)
    return llm.provider, urlunsplit((u.scheme, u.netloc.lower(), u.path, "", ""))


def is_official(llm):
    if llm.provider not in API_ENDPOINTS:
        return False
    from types import SimpleNamespace

    default = SimpleNamespace(provider=llm.provider, endpoint="", protocol="auto")
    return credential_scope(llm) == credential_scope(default)


def is_mask(value):
    return bool(value) and (
        any(c in value for c in "*•●…")
        or set(value) <= set("*•●· ")
        or value.startswith(("sk-***", "sk-…", "sk-..."))
    )
