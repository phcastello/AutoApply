"""The same draft resolution and public credential metadata for every screen."""

from config.ai_destination import DEFAULT_MODELS, credential_scope, destination, is_mask
from config.settings import LLMConfig, environment_credential, stored_credential


def resolve_draft(data, existing=None):
    if not isinstance(data, dict):
        raise ValueError("Envie uma configuração de IA JSON")
    baseline = existing.model_dump() if existing else LLMConfig().model_dump()
    # A changed provider must not inherit the previous endpoint or model.
    if "provider" in data and data["provider"] != baseline["provider"]:
        baseline.update(endpoint="", model="", protocol="auto", api_key="")
    baseline.update(
        {k: data[k] for k in ("provider", "endpoint", "model", "protocol") if k in data}
    )
    baseline["api_key"] = data.get("api_key") or ""
    draft = LLMConfig(**baseline)
    destination(draft.provider, draft.endpoint, draft.protocol)
    if is_mask(draft.api_key):
        raise ValueError(
            "Não informe uma máscara. Deixe a chave vazia para usar a credencial existente."
        )
    if draft.api_key and not draft.provider:
        raise ValueError("Selecione o provedor antes de informar uma chave.")
    if (
        existing
        and draft.api_key
        and draft.api_key == existing.api_key
        and credential_scope(draft) != credential_scope(existing)
    ):
        raise ValueError(
            "A chave anterior pertence a outro provedor ou destino. Informe uma credencial deste servidor."
        )
    if not draft.api_key and draft.provider:
        if existing and credential_scope(draft) == credential_scope(existing):
            draft.api_key = existing.api_key
        if not draft.api_key:
            draft.api_key = stored_credential(draft)
    return draft


def public_llm(llm):
    from core.ai_engine import check_ai_available

    data = llm.model_dump()
    key, env = environment_credential(llm)
    data.update(
        api_key="",
        has_api_key=bool(llm.api_key or key),
        credential_source="keyring" if llm.api_key else "environment" if key else "none",
        environment_variable=env,
        default_model=DEFAULT_MODELS.get(llm.provider, ""),
        available=check_ai_available(llm),
    )
    return data
