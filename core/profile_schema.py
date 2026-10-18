"""Validated import drafts. Source notes are never resume statements."""

import hashlib
import json
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Category = Literal[
    "experience", "education", "project", "skill", "language", "certification", "research", "other"
]


def normalized(value):
    value = unicodedata.normalize("NFKD", str(value)).casefold()
    return re.sub(r"\s+", " ", "".join(c for c in value if not unicodedata.combining(c))).strip()


def stable_id(prefix, value):
    return prefix + hashlib.sha256(normalized(value).encode()).hexdigest()[:24]


class ImportModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Activity(ImportModel):
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    start_date: str = ""
    end_date: str = ""
    date_notes: list[str] = []
    technologies: list[str] = []
    source_excerpt: str = ""


class ImportedFact(ImportModel):
    category: Category
    text: str = Field(min_length=1, max_length=20000)
    title: str = ""
    organization: str = ""
    start_date: str = ""
    end_date: str = ""
    date_notes: list[str] = []
    location: str = ""
    experience_type: str = ""
    technologies: list[str] = []
    url: str = ""
    proficiency: str = ""
    proficiency_basis: str = ""
    uncertainties: list[str] = []
    activities: list[Activity] = []
    source_excerpt: str = Field(min_length=1, max_length=60000)


class Contacts(ImportModel):
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone_country_code: str = ""
    phone: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    github_url: str = ""
    linkedin_url: str = ""
    portfolio_url: str = ""


class Constraint(ImportModel):
    text: str
    scope: str = "profile"
    source_excerpt: str = ""


class ImportedProfile(ImportModel):
    contacts: Contacts = Contacts()
    contact_notes: list[str] = []
    location_is_reference: bool = False
    entries: list[ImportedFact] = Field(default=[], max_length=200)
    constraints: list[Constraint] = []
    warnings: list[str] = []


def entry_fingerprint(entry):
    """Exact normalized factual content; never fuzzy-merge distinct employments."""
    fields = (
        "category",
        "title",
        "organization",
        "start_date",
        "end_date",
        "text",
        "technologies",
        "proficiency",
        "proficiency_basis",
        "activities",
    )
    content = {k: entry.get(k, [] if k in ("technologies", "activities") else "") for k in fields}
    return stable_id("fact-", json.dumps(content, ensure_ascii=False, sort_keys=True))


def deduplicate(entries, existing=()):
    seen = {e.get("import_key") or entry_fingerprint(e) for e in existing}
    result = []
    for entry in entries:
        key = entry.get("import_key") or entry_fingerprint(entry)
        if key not in seen:
            result.append({**entry, "import_key": key})
            seen.add(key)
    return result, len(entries) - len(result)


def public_draft(draft, source, text, *, mode, ai_used=False):
    data = draft.model_dump()
    entries = []
    seen_skills = set()
    for fact in data["entries"]:
        unique_technologies = []
        local_seen = set()
        for technology in fact["technologies"]:
            canonical = normalized(technology)
            if canonical in local_seen or (
                fact["category"] == "skill" and canonical in seen_skills
            ):
                continue
            local_seen.add(canonical)
            unique_technologies.append(technology)
        fact["technologies"] = unique_technologies
        if fact["category"] == "skill":
            seen_skills.update(local_seen)
        key = entry_fingerprint(fact)
        entries.append(
            dict(
                **fact,
                id=key,
                import_key=key,
                source=source,
                confirmed=False,
                import_mode=mode,
                import_engine="llm-schema" if ai_used else "structured-local",
                import_version=2,
                source_document_id=stable_id("doc-", text),
            )
        )
    data["entries"], duplicates = deduplicate(entries)
    data["constraints"] = [
        dict(**c, id=stable_id("rule-", c["scope"] + c["text"]), source=source, confirmed=False)
        for c in data["constraints"]
    ]
    data["contacts"] = {k: v for k, v in data["contacts"].items() if v}
    data["profile_suggestions"] = data["contacts"]  # Compatibility for old clients.
    data.update(
        source=source,
        confirmed=False,
        schema_version=2,
        mode=mode,
        ai_used=ai_used,
        document_id=stable_id("doc-", text),
        duplicate_count=duplicates,
    )
    return data
