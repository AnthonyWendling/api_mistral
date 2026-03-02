import re

def _slug(name):
    return re.sub(r"[^a-z0-9_-]", "-", name.lower()).strip("-") or "default"

names = [
    "Secteur d'activité",
    "Domaine d'application",
    "Famille de contrainte",
    "Univers",
    "Lots",
    "Affaires",
]
for n in names:
    print(n, "->", _slug(n))
