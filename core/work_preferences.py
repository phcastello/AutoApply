"""Location preferences use published location metadata; missing eligibility stays unknown."""

import re
import unicodedata


def normalized(value):
    value = "".join(c for c in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


COUNTRIES = {
    "br": ("brasil", "brazil", "br"),
    "us": ("united states", "united states of america", "estados unidos", "usa", "us", "u s"),
    "ca": ("canada", "ca"),
    "pt": ("portugal", "pt"),
    "gb": ("united kingdom", "reino unido", "uk", "great britain", "england"),
    "de": ("germany", "alemanha", "deutschland"),
    "es": ("spain", "espanha", "espana"),
    "fr": ("france", "franca"),
    "mx": ("mexico",),
    "ar": ("argentina",),
    "in": ("india",),
    "au": ("australia",),
}


def contains(value, term):
    return f" {normalized(term)} " in f" {normalized(value)} "


def country_codes(value):
    # Short country codes only when standalone or delimited, avoiding CA=California.
    return {code for code, names in COUNTRIES.items()
            if any(contains(value, name) for name in names if len(name) > 2)
            or normalized(value) == code and code != "ca"}


def location_checks(criteria, job):
    blockers, unknowns = [], []
    location = job.get("location") or ""
    mode = job.get("work_mode")
    modes = [normalized(m).replace(" ", "-") for m in criteria.work_modes]
    if criteria.remote_only:
        modes = ["remote"]
    if modes:
        if mode and mode not in modes:
            blockers.append("Modalidade difere da preferência")
        elif not mode:
            unknowns.append("Modalidade de trabalho não informada")
    if criteria.countries:
        accepted = set().union(*(country_codes(c) for c in criteria.countries))
        published = country_codes(location)
        direct = any(contains(location, c) for c in criteria.countries)
        if published and accepted and published.isdisjoint(accepted) and not direct:
            blockers.append("País publicado fora dos países aceitos")
        elif not direct and not (published & accepted):
            unknowns.append("País aceito não confirmado; confira elegibilidade para remoto")
    if mode != "remote" and criteria.locations:
        if not location:
            unknowns.append("Localização presencial não informada")
        elif not any(contains(location, city) for city in criteria.locations):
            if criteria.willing_to_relocate is not True:
                blockers.append("Localização fora das cidades aceitas")
            else:
                unknowns.append("Vaga exige conferir realocação para outra cidade")
    if mode == "remote":
        unknowns.append("Remoto não garante contratação no seu país; confira a elegibilidade na vaga")
    return blockers, unknowns


PREFERENCE_EXCLUSIONS = {
    "Palavra-chave excluída encontrada", "Empresa bloqueada",
    "Modalidade incompatível com remoto", "Modalidade difere da preferência",
    "País publicado fora dos países aceitos", "Localização fora das cidades aceitas",
    "Jornada publicada difere da preferência", "Senioridade publicada difere da preferência",
}


def outside_preferences(analysis):
    return any(b in PREFERENCE_EXCLUSIONS for b in analysis["blockers"])
