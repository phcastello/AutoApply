"""Location preferences use published location metadata; missing eligibility stays unknown."""

import re
import unicodedata


def normalized(value):
    value = "".join(
        c for c in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def contains(value, term):
    return f" {normalized(term)} " in f" {normalized(value)} "


def country_codes(value):
    from core.geo_names import COUNTRIES, countries_in

    return {COUNTRIES[c][0].lower() for c in countries_in(value)}


def location_checks(criteria, job):
    from types import SimpleNamespace

    from core.location_rules import location_eligibility

    result = location_eligibility(SimpleNamespace(country=""), criteria, job)
    return (
        result["reasons"] if result["category"] == "outside" else [],
        [p["message"] for p in result["pending"]],
    )


PREFERENCE_EXCLUSIONS = {
    "Palavra-chave excluída encontrada",
    "Empresa bloqueada",
    "Modalidade incompatível com remoto",
    "Modalidade difere da preferência",
    "País publicado fora dos países aceitos",
    "Localização fora das cidades aceitas",
    "Jornada publicada difere da preferência",
    "Senioridade publicada difere da preferência",
}


def outside_preferences(analysis):
    return analysis.get("eligibility", {}).get("category") == "outside" or any(
        b in PREFERENCE_EXCLUSIONS for b in analysis["blockers"]
    )
