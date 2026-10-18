"""One geographic policy for discovery, ranking, history and resume preparation.

Geographic interest never implies immigration or financial eligibility.
"""

import re

from core.geo_names import ALIASES, countries_in, country, fold

PRIORITIES = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1, None: 0}


def city(value):
    value = fold(value)
    if re.search(r"\b(estado|state|statewide)\b", value):
        return None
    parts = [p.strip() for p in re.split(r"[,;|/–—]|\s+-\s+", value) if p.strip()]
    if not parts:
        return None
    name = re.sub(r"\s*\((?:sp|pr|capital)\)\s*$", "", parts[0])
    name = re.sub(r"\s+(?:capital|city)$", "", name)
    if name in ALIASES or name in ("remote", "remoto", "sp", "pr", "europe", "europa", "worldwide"):
        return None
    if name == "sao paulo" and len(parts) == 1 and "capital" not in value and "city" not in value:
        return None
    states = {"sao paulo": "sp", "parana": "pr"}
    state = next((states.get(p, p) for p in parts[1:] if p in (*states, "sp", "pr")), "")
    nations = countries_in(value)
    if not state and len(parts) >= 3 and len(parts[1]) <= 3:
        state = parts[1]
    return name, state, next(iter(nations)) if len(nations) == 1 else ""


def published_countries(job, configured=()):
    explicit = {
        country(job[k]) for k in ("attendance_country", "country", "country_code") if job.get(k)
    }
    location = job.get("attendance_location") or job.get("location", "")
    literal = {
        country(c)
        for c in configured
        if len(fold(c)) > 2
        and re.search(r"(?<!\w)" + re.escape(fold(c)) + r"(?!\w)", fold(location))
    }
    return explicit | countries_in(location) | literal


def remote_scope(job, configured=()):
    """HQ is not a hiring jurisdiction. Only remote scope or residence wording counts."""

    def names_in(value):
        found = countries_in(value) | {
            country(c)
            for c in configured
            if len(fold(c)) > 2
            and re.search(r"(?<!\w)" + re.escape(fold(c)) + r"(?!\w)", fold(value))
        }
        if re.search(r"\b(?:us|uk|br)\s+(?:only|residents?)\b", fold(value)):
            found |= {
                country(code)
                for code in re.findall(r"\b(us|uk|br)\s+(?:only|residents?)\b", fold(value))
            }
        return found

    explicit = job.get("remote_countries") or []
    if isinstance(explicit, str):
        explicit = [explicit]
    scopes = [{country(c) for c in explicit}] if explicit else []
    excluded = {country(c) for c in (job.get("remote_excluded_countries") or [])}
    location = fold(job.get("location", ""))
    restriction = fold(job.get("remote_restrictions", ""))
    text = fold(job.get("description", "")) + " " + restriction
    if re.search(r"\b(?:remote|remoto)\b", location) and not re.search(
        r"\b(?:hq|headquarters)\b", location
    ):
        location_scope = names_in(location)
        if location_scope:
            scopes.append(location_scope)
    for sentence in re.split(r"[.;\n]", text):
        negative = re.search(
            r"\b(?:not (?:open|available|hiring)|cannot hire|can not hire|nao contrata|exclud(?:e|es|ing)|except)\b",
            sentence,
        )
        if negative:
            excluded |= names_in(sentence[negative.end() :])
            continue
        country_only = re.search(r"\b(?:us|uk|br)\s+(?:only|residents? only)\b", sentence)
        if country_only:
            scopes.append(names_in(country_only[0]))
        restriction_match = re.search(
            r"\b(?:residents? (?:of|in)|based in|must (?:live|reside) in|restricted to|only (?:in|from)|resid[ei]ntes? (?:no|do|em)|contratacao (?:no|em)|aberta? (?:ao|para o)|open to)\b",
            sentence,
        )
        if restriction_match and not re.search(
            r"\b(?:not|no|nao)\b", sentence[: restriction_match.start()]
        ):
            scope = names_in(sentence[restriction_match.end() :])
            if scope:
                scopes.append(scope)
    if restriction and not re.search(r"\b(?:not|nao|except|excluding)\b", restriction):
        scope = names_in(restriction)
        if scope:
            scopes.append(scope)
    worldwide = job.get("remote_worldwide") is True or bool(
        re.search(
            r"\b(?:remote worldwide|work from anywhere in the world|remoto mundial|abert[ao] ao mundo)\b",
            text + " " + location,
        )
    )
    if re.search(r"\b(?:not|nao)\s+(?:remote worldwide|remoto mundial)\b", text + " " + location):
        worldwide = False
    accepted = (set.intersection(*scopes) if scopes else set()) - excluded
    return accepted, worldwide and not scopes, excluded


def financial_compatibility(mobility, criteria, job):
    salary = job.get("salary")
    target, currency, period = (
        mobility.salary_min,
        mobility.salary_currency.upper().strip(),
        mobility.salary_period,
    )
    if not salary:
        if job.get("salary_ranges"):
            return dict(
                state="review",
                code="salary_context_unknown",
                message="Há faixas salariais publicadas; confirme região, moeda e período aplicáveis antes de comparar.",
            )
        return dict(
            state="review",
            code="salary_missing",
            message="Remuneração não informada; avaliar a oferta, sem descartar a vaga.",
        )
    if not isinstance(salary, dict):
        return dict(
            state="review",
            code="salary_unstructured",
            message="Confirme valor, moeda, período e regime da remuneração publicada.",
        )
    if target is None or not currency or not period:
        return dict(
            state="review",
            code="salary_target_missing",
            message="Defina um parâmetro financeiro com moeda e período para comparar a oferta.",
        )
    if (salary.get("currency") or "").upper() != currency or salary.get("period") != period:
        return dict(
            state="review",
            code="salary_units_differ",
            message="Moeda ou período diferentes; comparação financeira pendente, sem conversão presumida.",
        )
    low, high = salary.get("min"), salary.get("max", salary.get("min"))
    if (
        not isinstance(low, (int, float))
        or not isinstance(high, (int, float))
        or low < 0
        or high < low
    ):
        return dict(
            state="review",
            code="salary_incomplete",
            message="Faixa salarial incompleta ou inválida; confirmar valores.",
        )
    if high < target:
        return dict(
            state="below_target",
            code="salary_below_target",
            message="Faixa publicada abaixo do parâmetro financeiro; revisar a viabilidade da mudança.",
        )
    if low < target:
        return dict(
            state="review",
            code="salary_range_crosses_target",
            message="A faixa salarial cruza o mínimo desejado; confirmar a proposta.",
        )
    return dict(
        state="compatible",
        code="salary_meets_target",
        message="Valores publicados atingem o parâmetro informado; confirme regime bruto/líquido, custo de vida e contratação separadamente.",
    )


def location_eligibility(profile, criteria, job):
    mobility = criteria.mobility
    modes = ["remote"] if criteria.remote_only else list(criteria.work_modes)
    mode = {
        "onsite": "on-site",
        "on_site": "on-site",
        "presencial": "on-site",
        "hibrido": "hybrid",
        "remoto": "remote",
    }.get(fold(job.get("work_mode") or ""), job.get("work_mode"))
    residence_known = bool(getattr(profile, "country", "")) and not getattr(
        profile, "location_is_reference", False
    )
    residence = country(profile.country) if residence_known else ""
    destinations = {country(d.country): d for d in mobility.destinations}
    nations = published_countries(job, [*destinations, getattr(profile, "country", "")])
    nation = next(iter(nations)) if len(nations) == 1 else ""
    category, reasons, pending = "review", [], []
    relocation, target = None, nation

    def note(code, message, dimension="geography"):
        pending.append(dict(code=code, message=message, dimension=dimension))

    def relocate(candidates):
        nonlocal category, relocation, target
        selected = [c for c in candidates if c in destinations]
        if selected:
            target = max(selected, key=lambda c: PRIORITIES[destinations[c].priority])
        elif residence and residence in candidates and mobility.domestic_relocation is not False:
            target = residence
        else:
            if (
                not mobility.direct_locations
                and not destinations
                and mobility.international_relocation is not False
            ):
                note(
                    "mobility_unconfigured",
                    "Preferências de mobilidade ainda não definidas; revisar a localização.",
                )
                reasons.append(pending[-1]["message"])
                return
            category = "outside"
            reasons.append(
                "País fora dos destinos selecionados e das localidades diretamente aceitas."
            )
            return
        domestic = bool(residence and target == residence)
        willingness = (
            mobility.domestic_relocation if domestic else mobility.international_relocation
        )
        if willingness is False:
            category = "outside"
            reasons.append(
                "Mudança nacional não aceita." if domestic else "Mudança internacional não aceita."
            )
            return
        category, relocation = "relocation", True
        reasons.append(
            "Oportunidade com realocação para país selecionado; qualquer cidade pode ser avaliada."
            if not domestic
            else "Oportunidade com mudança nacional; avaliar as condições da oferta."
        )
        if willingness is None:
            note("relocation_availability_unknown", "Confirme disponibilidade para esta mudança.")
        if not residence_known:
            note(
                "residence_unknown",
                "Confirme sua residência atual; ela não é inferida dos destinos escolhidos.",
            )
        note(
            "relocation_conditions",
            mobility.relocation_conditions
            or "Avaliar remuneração, custo de vida, contratação e requisitos antes de decidir a mudança.",
            "relocation",
        )
        note(
            "cost_of_living",
            "Custo de vida, impostos e despesas da mudança ainda precisam ser avaliados.",
            "financial",
        )

    if mode not in ("remote", "hybrid", "on-site"):
        reasons.append("Modalidade não informada ou ambígua; confirme com a empresa.")
        note("work_mode_unknown", reasons[-1])
    elif (modes and mode not in modes) or (mode == "remote" and not mobility.remote_enabled):
        category = "outside"
        reasons.append("Modalidade não aceita nas preferências.")
    elif mode in ("hybrid", "on-site"):
        location = city(job.get("attendance_location") or job.get("location", ""))
        allowed = [city(c) for c in mobility.direct_locations]
        matching = [c for c in allowed if c and location and c[0] == location[0]]
        direct = [
            c
            for c in matching
            if (not c[1] or c[1] == location[1]) and (not c[2] or c[2] == location[2])
        ]
        if len(nations) > 1:
            note(
                "country_ambiguous",
                "Há países diferentes na localização; confirme onde o comparecimento será necessário.",
            )
            reasons.append(pending[-1]["message"])
        elif direct:
            category, relocation = "direct", False
            target = nation or direct[0][2]
            reasons.append(
                "Localidade diretamente aceita para comparecimento presencial ou híbrido."
            )
        elif nation:
            relocate({nation})
            if category == "relocation" and not location:
                note(
                    "city_unknown",
                    "País selecionado; confirme a cidade para avaliar a mudança. Não é necessário cadastrar o município nas preferências.",
                )
        elif matching:
            reasons.append("Confirme estado e país da cidade de comparecimento.")
            note("city_ambiguous", reasons[-1])
        else:
            reasons.append(
                "Localização presencial incompleta; confirme cidade e país, sem incompatibilidade presumida."
            )
            note("country_unknown", reasons[-1])
    elif mode == "remote":
        accepted, worldwide, excluded = remote_scope(
            job, [*destinations, getattr(profile, "country", "")]
        )
        if residence_known and residence not in excluded and (residence in accepted or worldwide):
            category, relocation, target = "remote", False, residence
            reasons.append("Trabalho remoto explicitamente permitido a partir da sua residência.")
        elif (accepted & destinations.keys()) or (
            worldwide and residence in excluded and destinations.keys() - excluded
        ):
            relocate(accepted if accepted else destinations.keys() - excluded)
            reasons.append(
                "A vaga é remota somente após residir em um país permitido; não é remoto imediatamente elegível na residência atual."
            )
        elif not residence_known:
            reasons.append(
                "Residência atual não confirmada; localizações de referência não comprovam elegibilidade remota."
            )
            note("residence_unknown", reasons[-1])
        elif accepted or residence in excluded:
            category = "outside"
            reasons.append(
                "Residência fora do escopo remoto e nenhum país permitido está nos destinos de realocação."
            )
        else:
            reasons.append(
                "Remoto sem confirmação de contratação e trabalho a partir da sua residência."
            )
            note("remote_scope_unknown", reasons[-1])
        if (
            job.get("timezone_restriction")
            or job.get("hiring_restriction")
            or re.search(
                r"\b(?:must|only|required|obrigatori[oa]).{0,45}(?:time zone|timezone|fuso|work authorization|autorizacao de trabalho)\b",
                fold(job.get("description", "")),
            )
        ):
            note(
                "remote_hiring_restriction",
                "Há restrição de fuso ou contratação; confirme se ela permite trabalhar da sua residência.",
                "hiring",
            )
            if category == "remote":
                category = "review"

    authorizations = {country(c) for c in mobility.work_authorization_countries}
    sponsorship = job.get("visa_sponsorship", job.get("sponsorship_available"))
    description = fold(job.get("description", ""))
    if sponsorship is None and re.search(
        r"\b(?:no|not|without).{0,35}(?:visa sponsorship|sponsor.{0,15}visa)\b", description
    ):
        sponsorship = False
    if target and target in authorizations:
        immigration = dict(
            state="declared",
            message="Autorização de trabalho informada pelo candidato para este país; confirmar requisitos da vaga.",
        )
    elif criteria.needs_sponsorship is True and sponsorship is False:
        immigration = dict(
            state="incompatible",
            message="Candidato informou necessidade de patrocínio; a vaga declara que não oferece patrocínio de visto.",
        )
        note("sponsorship_unavailable", immigration["message"], "immigration")
    else:
        immigration = dict(
            state="review",
            message="Autorização de trabalho e elegibilidade migratória não confirmadas; aceitar mudar não comprova autorização.",
        )
        note("work_authorization_unknown", immigration["message"], "immigration")
        if sponsorship is None:
            note(
                "sponsorship_unknown",
                "Patrocínio de visto não informado; confirmar com a empresa quando necessário.",
                "immigration",
            )
    financial = financial_compatibility(mobility, criteria, job)
    if financial["state"] != "compatible":
        note(financial["code"], financial["message"], "financial")
    if not job.get("required_languages"):
        note(
            "language_requirements_unknown",
            "Idiomas exigidos e níveis ainda precisam ser confirmados.",
            "professional",
        )
    else:
        languages = job["required_languages"]
        if isinstance(languages, str):
            languages = [languages]
        note(
            "language_proficiency_review",
            "Idiomas publicados: "
            + ", ".join(languages)
            + "; confirmar níveis e evidências do perfil.",
            "professional",
        )
    if not job.get("start_date"):
        note(
            "start_date_unknown",
            "Data de início não informada; combinar com a empresa.",
            "availability",
        )
    elif mobility.available_from:
        from datetime import date

        try:
            conflict = date.fromisoformat(job["start_date"]) < date.fromisoformat(
                mobility.available_from
            )
        except (ValueError, TypeError):
            note(
                "start_date_ambiguous",
                "Data publicada ou disponibilidade aproximada; confirmar o início.",
                "availability",
            )
        else:
            if conflict:
                note(
                    "start_date_conflict",
                    "Início publicado anterior à disponibilidade informada; negociar a data.",
                    "availability",
                )
    destination = destinations.get(target)
    return dict(
        state="eligible"
        if category in ("direct", "remote")
        else "incompatible"
        if category == "outside"
        else "review",
        category=category,
        reasons=reasons,
        country=target,
        country_priority=PRIORITIES[destination.priority] if destination else 0,
        country_tier=destination.priority if destination else None,
        relocation_required=relocation,
        immigration=immigration,
        financial=financial,
        pending=pending,
        available_from=mobility.available_from,
        availability_notes=mobility.availability_notes,
    )


def geographic_rank(analysis):
    geography = analysis.get("eligibility", {})
    return (
        geography.get("category") != "outside",
        analysis["score"] + 2 * geography.get("country_priority", 0),
        analysis["score"],
        geography.get("relocation_required") is False,
    )


def search_locations(criteria):
    """Country-wide queries for legacy searchers; no municipality enumeration."""
    mobility = criteria.mobility
    if criteria.remote_only:
        return ["Remote"]
    values = list(mobility.direct_locations)
    if mobility.international_relocation is not False or mobility.domestic_relocation is not False:
        values.extend(d.country for d in mobility.destinations)
    if mobility.remote_enabled:
        values.append("Remote")
    return list(dict.fromkeys(values)) or [""]
