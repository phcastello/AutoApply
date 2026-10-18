"""Application configuration and settings models.

Implements: FR-001 (data directory), FR-003 (configuration model),
            NFR-QW1 (keyring integration).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from config.ai_destination import credential_scope, is_mask, is_official
from core.profile_schema import Activity

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyring helpers — lazy-checked, graceful fallback to plaintext
# ---------------------------------------------------------------------------

_keyring_available: bool | None = None  # lazy-init sentinel
KEYRING_SERVICE = "autoapply"
KEYRING_KEY_NAME = "llm_api_key"


def _credential_name(llm) -> str:
    scope = hashlib.sha256(credential_scope(llm)[1].encode()).hexdigest()[:24]
    return f"{KEYRING_KEY_NAME}:{llm.provider}:{scope}"


def environment_credential(llm) -> tuple[str, str]:
    """Environment secrets are bound to a provider and destination, never global."""
    names = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
    }
    name = names.get(llm.provider)
    if name and is_official(llm) and os.environ.get(name):
        return os.environ[name], name
    if (
        os.environ.get("AUTOAPPLY_LLM_API_KEY")
        and os.environ.get("AUTOAPPLY_LLM_PROVIDER") == llm.provider
    ):
        scope = LLMConfig(
            provider=llm.provider, endpoint=os.environ.get("AUTOAPPLY_LLM_ENDPOINT", "")
        )
        if credential_scope(scope) == credential_scope(llm):
            return os.environ["AUTOAPPLY_LLM_API_KEY"], "AUTOAPPLY_LLM_API_KEY"
    return "", ""


def stored_credential(llm) -> str:
    if not llm.provider or not _check_keyring():
        return ""
    import keyring

    return keyring.get_password(KEYRING_SERVICE, _credential_name(llm)) or ""


def remove_credential(llm) -> None:
    if _check_keyring():
        import keyring

        legacy_scope = (
            hashlib.sha256(llm.endpoint.encode()).hexdigest()[:16] if llm.endpoint else "default"
        )
        for name in (_credential_name(llm), f"{KEYRING_KEY_NAME}:{llm.provider}:{legacy_scope}"):
            try:
                keyring.delete_password(KEYRING_SERVICE, name)
            except keyring.errors.PasswordDeleteError:
                pass
    llm.api_key = ""


def _check_keyring() -> bool:
    """Return True if the OS keyring backend is usable. Result is cached."""
    global _keyring_available
    if _keyring_available is not None:
        return _keyring_available
    try:
        import keyring

        keyring.get_password(KEYRING_SERVICE, "__probe__")
        _keyring_available = True
    except Exception:
        _logger.warning(
            "keyring unavailable — API keys must be supplied through the session environment"
        )
        _keyring_available = False
    return _keyring_available


class CareerEntry(BaseModel):
    """One user-confirmed fact, with its original role and dates attached."""

    id: str
    category: str = "experience"
    text: str
    title: str = ""
    organization: str = ""
    start_date: str = ""
    end_date: str = ""
    location: str = ""
    technologies: list[str] = []
    url: str = ""
    experience_type: str = ""
    proficiency: str = ""
    source: str = "manual"
    confirmed: bool = False
    source_excerpt: str = ""
    import_key: str = ""
    import_mode: str = ""
    import_engine: str = ""
    import_version: int = 0
    source_document_id: str = ""
    date_notes: list[str] = []
    activities: list[Activity] = []
    proficiency_basis: str = ""
    uncertainties: list[str] = []


class UserProfile(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone_country_code: str = "+1"
    phone: str
    address_line1: str = ""
    address_line2: str = ""
    city: str
    state: str
    zip_code: str = ""
    country: str = "United States"
    bio: str
    linkedin_url: str | None = None
    portfolio_url: str | None = None
    fallback_resume_path: str | None = None
    screening_answers: dict = {}
    github_url: str = ""
    professional_links: list[str] = []
    career_entries: list[CareerEntry] = []
    generation_constraints: list[dict] = []
    contact_notes: list[str] = []
    location_is_reference: bool = False

    # Backward-compatible property — used by AI engine prompts and Lever/Indeed
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    # Backward-compatible property — formatted location string
    @property
    def location(self) -> str:
        if self.location_is_reference:
            return ""
        parts = [self.city, self.state]
        loc = ", ".join(p for p in parts if p)
        if self.country and self.country != "United States":
            loc = f"{loc}, {self.country}" if loc else self.country
        return loc

    # Full phone with country code
    @property
    def phone_full(self) -> str:
        if self.phone_country_code and not self.phone.startswith("+"):
            return f"{self.phone_country_code}{self.phone}"
        return self.phone

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_fields(cls, data):
        """Accept old config format with full_name and location strings."""
        if isinstance(data, dict):
            # Migrate full_name → first_name + last_name
            if "full_name" in data and "first_name" not in data:
                parts = data.pop("full_name", "").split(None, 1)
                data["first_name"] = parts[0] if parts else ""
                data["last_name"] = parts[1] if len(parts) > 1 else ""
            # Migrate location → city + state
            if "location" in data and "city" not in data:
                loc = data.pop("location", "")
                parts = [p.strip() for p in loc.split(",")]
                data["city"] = parts[0] if parts else ""
                data["state"] = parts[1] if len(parts) > 1 else ""
                if len(parts) > 2:
                    data["country"] = parts[2]
        return data


class RelocationDestination(BaseModel):
    country: str = Field(min_length=1, max_length=100)
    priority: Literal["S", "A", "B", "C", "D"] | None = None


class MobilityPreferences(BaseModel):
    direct_locations: list[str] = []
    domestic_relocation: bool | None = None
    international_relocation: bool | None = None
    destinations: list[RelocationDestination] = []
    relocation_conditions: str = ""
    remote_enabled: bool = True
    available_from: str = ""
    availability_notes: str = ""
    work_authorization_countries: list[str] = []
    salary_min: float | None = Field(default=None, ge=0)
    salary_currency: str = ""
    salary_period: Literal["annual", "monthly", "hourly"] | None = None

    @model_validator(mode="after")
    def unique_destinations(self):
        from core.geo_names import country

        keys = [country(d.country) for d in self.destinations]
        if any(not k for k in keys) or len(keys) != len(set(keys)):
            raise ValueError("Escolha cada país de destino uma única vez")
        return self


class SearchCriteria(BaseModel):
    job_titles: list[str]
    locations: list[str]
    attendance_cities: list[str] = []  # Preserve older configurations, too.
    mobility: MobilityPreferences = MobilityPreferences()
    remote_only: bool = False
    salary_min: int | None = None
    keywords_include: list[str] = []
    keywords_exclude: list[str] = []
    experience_levels: list[str] = []
    areas: list[str] = []
    countries: list[str] = []
    work_modes: list[str] = []
    weekly_hours: int | None = Field(default=None, ge=1, le=168)
    employment_types: list[str] = []
    contract_types: list[str] = []
    accepted_languages: list[str] = []
    resume_language: str = "auto"
    willing_to_relocate: bool | None = None
    needs_sponsorship: bool | None = None
    # Public ATS board identifiers, editable in the dashboard.
    greenhouse_boards: list[str] = ["stripe"]
    lever_boards: list[str] = ["ciandt"]
    max_results: int = Field(default=20, ge=1, le=100)
    source_names: dict[str, str] = {}

    @model_validator(mode="before")
    @classmethod
    def migrate_mobility(cls, data):
        if isinstance(data, dict) and ("mobility" not in data or data["mobility"] is None):
            data = dict(data)
            modes = data.get("work_modes", [])
            willingness = data.get("willing_to_relocate")
            from core.geo_names import country

            legacy_destinations = {}
            for name in data.get("countries", []):
                if country(name):
                    legacy_destinations.setdefault(country(name), name)
            data["mobility"] = dict(
                direct_locations=list(
                    dict.fromkeys([*data.get("attendance_cities", []), *data.get("locations", [])])
                ),
                domestic_relocation=willingness if willingness is not None else False,
                international_relocation=willingness,
                destinations=[dict(country=c) for c in legacy_destinations.values()],
                remote_enabled=bool(data.get("remote_only") or not modes or "remote" in modes),
                salary_min=data.get("salary_min"),
            )
        return data


def merge_search_criteria(existing, patch):
    """Legacy editors can still edit their fields without leaving two active policies."""
    merged = {**existing, **patch}
    if "mobility" in patch:
        if not isinstance(patch["mobility"], dict):
            return merged
        merged["mobility"] = {**existing.get("mobility", {}), **patch["mobility"]}
        if isinstance(patch["mobility"].get("direct_locations"), list):
            merged["locations"] = list(patch["mobility"]["direct_locations"])
        if isinstance(patch["mobility"].get("destinations"), list) and all(
            isinstance(d, dict) and isinstance(d.get("country"), str)
            for d in patch["mobility"]["destinations"]
        ):
            merged["countries"] = [d["country"] for d in patch["mobility"]["destinations"]]
    elif any(
        k in patch
        for k in (
            "locations",
            "attendance_cities",
            "countries",
            "willing_to_relocate",
            "remote_only",
            "work_modes",
        )
    ):
        mobility = dict(existing.get("mobility", {}))
        if "locations" in patch or "attendance_cities" in patch:
            if any(
                k in patch and not isinstance(patch[k], list)
                for k in ("locations", "attendance_cities")
            ):
                return merged
            mobility["direct_locations"] = list(
                dict.fromkeys([*patch.get("attendance_cities", []), *patch.get("locations", [])])
            )
        if "countries" in patch:
            if not isinstance(patch["countries"], list):
                return merged
            mobility["destinations"] = [dict(country=c) for c in patch["countries"]]
        if "willing_to_relocate" in patch:
            mobility.update(
                domestic_relocation=patch["willing_to_relocate"],
                international_relocation=patch["willing_to_relocate"],
            )
        if patch.get("remote_only") is True:
            mobility["remote_enabled"] = True
        elif isinstance(patch.get("work_modes"), list):
            mobility["remote_enabled"] = not patch["work_modes"] or "remote" in patch["work_modes"]
        merged["mobility"] = mobility
    return merged


class ScheduleConfig(BaseModel):
    enabled: bool = False
    days_of_week: list[str] = ["mon", "tue", "wed", "thu", "fri"]
    start_time: str = "09:00"  # HH:MM in 24-hour local time
    end_time: str = "17:00"  # HH:MM in 24-hour local time


class LLMConfig(BaseModel):
    provider: str = ""  # "anthropic" | "openai" | "google" | "deepseek"
    api_key: str = ""
    model: str = ""  # Empty = use default for provider
    endpoint: str = ""
    protocol: str = "auto"
    credential_version: int = 2


class ResumeReuseConfig(BaseModel):
    """Configuration for smart resume reuse via Knowledge Base assembly."""

    enabled: bool = True
    min_score: float = 0.0
    min_experience_bullets: int = 6
    scoring_method: str = "auto"  # "tfidf" | "onnx" | "auto"
    cover_letter_strategy: str = "generate"  # "generate" | "template"


class LatexConfig(BaseModel):
    """Configuration for LaTeX resume compilation."""

    template: str = "classic"  # template name in templates/latex/
    font_family: str = "helvetica"  # helvetica, times, palatino
    font_size: int = 11  # 10, 11, 12
    margin: str = "0.75in"


class BotConfig(BaseModel):
    enabled_platforms: list[str] = ["linkedin", "indeed"]
    min_match_score: int = 75
    max_applications_per_day: int = 50
    delay_between_applications_seconds: int = 45
    search_interval_seconds: int = 1800
    apply_mode: str = "watch"  # Automatic submission requires explicit opt-in.
    watch_mode: bool = False  # Deprecated: use apply_mode instead
    cover_letter_enabled: bool = True
    cover_letter_template: str = ""
    schedule: ScheduleConfig = ScheduleConfig()


class AppConfig(BaseModel):
    profile: UserProfile
    search_criteria: SearchCriteria
    bot: BotConfig = BotConfig()
    llm: LLMConfig = LLMConfig()
    resume_reuse: ResumeReuseConfig = ResumeReuseConfig()
    latex: LatexConfig = LatexConfig()
    company_blacklist: list[str] = []
    version: str = "2.0"


def get_data_dir() -> Path:
    override = os.environ.get("AUTOAPPLY_DATA_DIR")
    return Path(override).expanduser().resolve() if override else Path.home() / ".autoapply"


def load_config() -> AppConfig | None:
    config_path = get_data_dir() / "config.json"
    if not config_path.exists():
        return None
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    config = AppConfig(**data)

    # Retrieve API key from keyring if available
    if config.llm.provider and _check_keyring():
        import keyring

        credential_name = _credential_name(config.llm)
        stored_key = keyring.get_password(KEYRING_SERVICE, credential_name)
        if not stored_key and "credential_version" not in data.get("llm", {}):
            old_scope = (
                hashlib.sha256(config.llm.endpoint.encode()).hexdigest()[:16]
                if config.llm.endpoint
                else "default"
            )
            stored_key = keyring.get_password(
                KEYRING_SERVICE, f"{KEYRING_KEY_NAME}:{config.llm.provider}:{old_scope}"
            )
            if stored_key:
                keyring.set_password(KEYRING_SERVICE, credential_name, stored_key)
        if (
            not stored_key
            and "credential_version" not in data.get("llm", {})
            and "endpoint" not in data.get("llm", {})
        ):
            # One-time migration from the upstream's shared provider key slot.
            stored_key = keyring.get_password(KEYRING_SERVICE, KEYRING_KEY_NAME)
            if stored_key:
                keyring.set_password(KEYRING_SERVICE, credential_name, stored_key)
                config.llm.api_key = stored_key
                _save_config_raw(config, strip_api_key=True)
        if stored_key:
            config.llm.api_key = stored_key
        elif config.llm.api_key:
            # Migration: move plaintext key into keyring
            keyring.set_password(KEYRING_SERVICE, credential_name, config.llm.api_key)
            _save_config_raw(config, strip_api_key=True)
            _logger.info("Migrated API key from config.json to OS keyring")

    return config


def save_config(config: AppConfig) -> None:
    if is_mask(config.llm.api_key):
        raise ValueError(
            "Uma máscara não é uma credencial. Deixe o campo vazio para manter a chave."
        )
    # Store API key in keyring if possible
    if config.llm.api_key and not _check_keyring():
        raise ValueError(
            "Keyring indisponível. Use AUTOAPPLY_LLM_API_KEY nesta sessão; a chave não será gravada em texto puro."
        )
    if config.llm.api_key and _check_keyring():
        import keyring

        keyring.set_password(KEYRING_SERVICE, _credential_name(config.llm), config.llm.api_key)

    _save_config_raw(config, strip_api_key=True)


def _save_config_raw(config: AppConfig, strip_api_key: bool = False) -> None:
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    config_path = data_dir / "config.json"
    dump = config.model_dump()
    if strip_api_key:
        dump.get("llm", {})["api_key"] = ""
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(dump, f, indent=2)


def is_first_run() -> bool:
    return not (get_data_dir() / "config.json").exists()
