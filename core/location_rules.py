"""Conservative geographical eligibility, independent from relevance scoring."""

import re
import unicodedata


def fold(value):
    return re.sub(
        r"\s+",
        " ",
        "".join(
            c
            for c in unicodedata.normalize("NFKD", str(value).lower())
            if not unicodedata.combining(c)
        ),
    ).strip()


def country(value):
    value = fold(value)
    return {
        "br": "brasil",
        "brazil": "brasil",
        "brasil": "brasil",
        "us": "estados unidos",
        "usa": "estados unidos",
        "united states": "estados unidos",
        "eua": "estados unidos",
        "united states of america": "estados unidos",
    }.get(value, value)


def city(value):
    """A city is a complete component, never a substring/state abbreviation."""
    value = fold(value)
    if re.search(r"\b(estado|state|statewide)\b", value):
        return None
    parts = [p.strip() for p in re.split(r"[,;|/–—]|\s+-\s+", value) if p.strip()]
    if not parts:
        return None
    name = re.sub(r"\s*\((?:sp|pr|capital)\)\s*$", "", parts[0])
    name = re.sub(r"\s+(?:capital|city)$", "", name)
    if name in ("remote", "remoto", "sp", "pr", "brasil", "brazil"):
        return None
    # São Paulo without municipality/state distinction is ambiguous in source data.
    if name == "sao paulo" and len(parts) == 1 and "capital" not in value and "city" not in value:
        return None
    states = {"sao paulo": "sp", "parana": "pr"}
    state = next((states.get(p, p) for p in parts[1:] if p in (*states, "sp", "pr")), "")
    nation = next((country(p) for p in parts[1:] if country(p) in ("brasil", "estados unidos")), "")
    return name, state, nation


def location_eligibility(profile, criteria, job):
    modes = list(criteria.work_modes)
    if criteria.remote_only:
        modes = ["remote"]
    mode = {
        "onsite": "on-site",
        "on_site": "on-site",
        "presencial": "on-site",
        "hibrido": "hybrid",
        "remoto": "remote",
    }.get(fold(job.get("work_mode") or ""), job.get("work_mode"))
    reasons, state = [], "eligible"

    def decide(value, message):
        nonlocal state
        if value == "incompatible" or state == "eligible":
            state = value
        reasons.append(message)

    if mode not in ("remote", "hybrid", "on-site"):
        decide("review", "Modalidade não informada ou ambígua; confirme com a empresa.")
    elif modes and mode not in modes:
        decide("incompatible", "Modalidade não aceita nas preferências.")
    elif mode in ("hybrid", "on-site"):
        allowed = getattr(criteria, "attendance_cities", []) or criteria.locations
        location = city(job.get("attendance_location") or job.get("location", ""))
        if not location:
            decide(
                "review",
                "Cidade de comparecimento ausente ou ambígua; estado não equivale a cidade.",
            )
        elif allowed:
            candidates = [city(c) for c in allowed]
            matching = [c for c in candidates if c and c[0] == location[0]]
            if not matching:
                decide("incompatible", "Comparecimento fora das cidades aceitas.")
            elif not any(
                (not c[1] or c[1] == location[1]) and (not c[2] or c[2] == location[2])
                for c in matching
            ):
                if not location[1] or not location[2]:
                    decide("review", "Confirme estado e país da cidade de comparecimento.")
                else:
                    decide("incompatible", "Estado ou país do comparecimento incompatível.")
            else:
                reasons.append("Cidade e modalidade de comparecimento aceitas.")
        else:
            decide("review", "Defina as cidades em que aceita comparecimento.")
    elif mode == "remote":
        if getattr(profile, "location_is_reference", False):
            decide(
                "review",
                "Localização do perfil é referência de teste; confirme residência antes de avaliar elegibilidade remota.",
            )
        residence = country(profile.country)
        eligible = job.get("remote_countries") or []
        eligible = [country(c) for c in eligible]
        location = fold(job.get("location", ""))
        description = fold(job.get("description", ""))
        restriction = fold(job.get("remote_restrictions", ""))
        text = " ".join((location, description, restriction))
        if not eligible:
            if re.search(
                r"\b(?:remote|remoto)\s*(?:[-–—,:()]\s*)?(?:brazil|brasil)\b|\b(?:brazil|brasil)\s*[-–—,:()]\s*(?:remote|remoto)\b",
                location,
            ) or re.search(
                r"(?:open to|residents? (?:of|in)|based in|resid[ei]ntes? (?:no|do)|contratacao (?:no|em)|aberta? (?:ao|para o))\s+(?:brazil|brasil)\b",
                text,
            ):
                eligible = ["brasil"]
            elif re.search(
                r"\b(?:us|usa|united states|eua)\s*[-–—,:()]\s*remote\b|\bremote\s*[-–—,:()]\s*(?:us|usa|united states)\b|(?:restricted to|only|residents of|based in|somente|restrit[ao]s? (?:aos?|nos?))\s+(?:the )?(?:us|usa|united states|eua)\b",
                text,
            ):
                eligible = ["estados unidos"]
        worldwide = job.get("remote_worldwide") is True or bool(
            re.search(
                r"\b(?:remote worldwide|work from anywhere in the world|remoto mundial|abert[ao] ao mundo)\b",
                text,
            )
        )
        if eligible and residence not in eligible:
            decide(
                "incompatible",
                "Residência fora dos países explicitamente aceitos para trabalho remoto.",
            )
        elif not residence or not (eligible or worldwide):
            decide("review", "Remoto sem confirmação de elegibilidade para sua residência.")
        else:
            reasons.append("Trabalho remoto explicitamente permitido para sua residência.")
        # Time-zone and hiring restrictions must be checked separately from HQ.
        if (
            job.get("timezone_restriction")
            or job.get("hiring_restriction")
            or re.search(
                r"\b(?:must|only|required|obrigatori[oa]).{0,45}(?:time zone|timezone|fuso|work authorization|autorizacao de trabalho)\b",
                text,
            )
        ):
            decide("review", "Há restrição de fuso ou contratação; confirme sua elegibilidade.")
    return dict(state=state, reasons=reasons)
