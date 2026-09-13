"""Stable ISO keys; aggregates never become supplying countries."""
import pycountry

ALIASES = {
    "china, mainland": "CHN", "china": "CHN", "usa": "USA",
    "united states": "USA", "united states of america": "USA",
    "russian federation": "RUS", "russia": "RUS", "republic of korea": "KOR",
    "korea, republic of": "KOR", "rep. of korea": "KOR", "viet nam": "VNM",
    "bolivia (plurinational state of)": "BOL", "iran (islamic republic of)": "IRN",
    "china, hong kong sar": "HKG", "china, macao sar": "MAC",
}
AGGREGATES = {"", "W00", "WLD", "WORLD", "TOTAL", "OTHER", "OTHER COUNTRIES", "AREAS, NES"}


def normalize(value, *, code=None):
    text = str(value or "").strip()
    token = str(code or text).strip().upper()
    if token in AGGREGATES:
        return None
    country = pycountry.countries.get(alpha_3=token)
    if country:
        return country.alpha_3
    if text.lower() in ALIASES:
        return ALIASES[text.lower()]
    try:
        return pycountry.countries.lookup(text).alpha_3
    except LookupError:
        raise ValueError(f"Unmapped country: {text!r} ({code!r}); review registry")


def label(code):
    return {"USA": "United States", "RUS": "Russian Federation", "CHN": "China"}.get(
        code, pycountry.countries.get(alpha_3=code).name)
