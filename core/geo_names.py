"""Country names are metadata, never a list of candidate destinations."""

import re
import unicodedata


def fold(value):
    return re.sub(
        r"\s+",
        " ",
        "".join(
            c
            for c in unicodedata.normalize("NFKD", str(value).casefold())
            if not unicodedata.combining(c)
        ),
    ).strip()


# Canonical names and common published aliases. Unlisted names still match literally.
COUNTRIES = {
    "brasil": ("BR", "Brazil", "Brasil"),
    "paises baixos": (
        "NL",
        "Netherlands",
        "The Netherlands",
        "Países Baixos",
        "Holanda",
        "Nederland",
    ),
    "irlanda": ("IE", "Ireland", "Irlanda", "Éire"),
    "alemanha": ("DE", "Germany", "Alemanha", "Deutschland"),
    "japao": ("JP", "Japan", "Japão", "日本"),
    "suica": ("CH", "Switzerland", "Suíça", "Schweiz", "Suisse"),
    "noruega": ("NO", "Norway", "Noruega", "Norge"),
    "coreia do sul": ("KR", "South Korea", "Coreia do Sul", "Republic of Korea", "대한민국"),
    "austria": ("AT", "Austria", "Áustria", "Österreich"),
    "singapura": ("SG", "Singapore", "Singapura"),
    "luxemburgo": ("LU", "Luxembourg", "Luxemburgo"),
    "belgica": ("BE", "Belgium", "Bélgica", "Belgique", "België"),
    "reino unido": (
        "GB",
        "UK",
        "United Kingdom",
        "Reino Unido",
        "Great Britain",
        "England",
        "Scotland",
        "Wales",
        "Northern Ireland",
    ),
    "australia": ("AU", "Australia", "Austrália"),
    "canada": ("CA", "Canada", "Canadá"),
    "estados unidos": (
        "US",
        "USA",
        "United States",
        "United States of America",
        "Estados Unidos",
        "EUA",
    ),
    "dinamarca": ("DK", "Denmark", "Dinamarca", "Danmark"),
    "suecia": ("SE", "Sweden", "Suécia", "Sverige"),
    "finlandia": ("FI", "Finland", "Finlândia", "Suomi"),
    "nova zelandia": ("NZ", "New Zealand", "Nova Zelândia"),
    "portugal": ("PT", "Portugal"),
    "italia": ("IT", "Italy", "Itália", "Italia"),
    "franca": ("FR", "France", "França"),
    "espanha": ("ES", "Spain", "Espanha", "España"),
    "polonia": ("PL", "Poland", "Polônia", "Polska"),
    "mexico": ("MX", "Mexico", "México"),
    "argentina": ("AR", "Argentina"),
    "india": ("IN", "India", "Índia"),
    "china": ("CN", "China"),
}
ALIASES = {fold(alias): name for name, aliases in COUNTRIES.items() for alias in (*aliases, name)}


def country(value):
    return ALIASES.get(fold(value), fold(value))


def countries_in(value):
    """Use full names or delimited codes; CA in a US address is not Canada."""
    text = fold(value)
    found = set()
    for alias, canonical in sorted(ALIASES.items(), key=lambda item: -len(item[0])):
        if len(alias) <= 2:
            if alias in {"ca", "de", "in"}:
                continue
            match = re.fullmatch(re.escape(alias), text) or re.search(
                r"(?:[,;|(]|\s[-–—]\s)\s*" + re.escape(alias) + r"\s*\)?$", text
            )
        else:
            match = re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text)
        if match:
            found.add(canonical)
    # Northern Ireland is a UK location, rather than two conflicting countries.
    if "northern ireland" in text:
        found.discard("irlanda")
    return found
