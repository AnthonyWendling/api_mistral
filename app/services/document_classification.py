"""
Taxonomie pour la classification des documents (contraintes, univers, secteur, domaine, lots).
Utilisée pour créer des collections par catégorie et classifier les documents avec l'IA.
"""
import json
import re
from typing import Any

from app.services.mistral_agent import get_client

MAX_TEXT_LENGTH = 100_000

# --- Famille de contrainte ---
FAMILLES_CONTRAINTE = [
    "Contrainte d'implantation",
    "Contrainte d'hygiène",
    "Contrainte de production",
    "Contrainte de qualité",
    "Contrainte environnementale",
    "Contrainte ergonomique",
    "Contrainte financière",
    "Contrainte maintenance",
    "Contrainte organisationnelle",
    "Contrainte planning",
    "Contrainte produit",
    "Contrainte projet",
    "Contrainte réglementaire",
    "Contrainte sécurité",
    "Contrainte technique",
    "Contrainte de confidentialité",
    "Contrainte d'accessibilité",
    "Contrainte logistique",
    "Contrainte de performance",
    "Contrainte d'intégration",
]

# --- Univers ---
UNIVERS = [
    "Milieu",
    "Matière",
    "Méthode",
    "Main d'œuvre",
    "Matériel",
    "Sécurité",
    "Qualité",
]

# --- Secteur d'activité ---
SECTEURS_ACTIVITE = [
    "Générique",
    "Agroalimentaire",
    "Cosmétique",
    "Mécanique",
    "Pharmaceutique",
    "Chimie",
    "Papeterie",
    "Menuiserie",
    "Packaging",
]

# --- Domaine d'application ---
DOMAINES_APPLICATION = [
    "Process",
    "Logistique",
    "Utilités",
    "Infrastructure",
    "Autres",
    "Étude de flux",
    "Nettoyage",
    "PID",
    "Étude de sol",
    "Sécurité",
    "ATEX",
    "Normes",
    "Chantier",
    "DAO / CAO",
    "Conditionnement",
]

# --- Lots ---
LOTS = [
    "Electricité / Automatisme",
    "Machine / Equipement",
    "Convoyeur",
    "Utilité : Air comprimé",
    "Utilité : Équipement thermique",
    "Second œuvre : Bâtiment interne",
    "VRD (voirie Réseau Divers)",
    "Construction métallique",
    "Transfert équipements",
    "Equipements frigorifiques et Isolation / calorifugeage",
    "Utilité : Isolation / calorifugeage",
    "Salle blanche",
    "Etudes / ingénierie / calculs",
    "Génie civil / gros œuvre",
    "Utilité : Hydraulique et pneumatique",
    "Utilité : Réseau / Informatique",
    "Manutention / levage",
    "Nettoyage industriel / NEP",
    "Rack / stockage / Palettier / Echafaudage",
    "Utilité : Incendie",
    "Utilité : Traitement de l'air",
    "Tuyauteur - Chaudronnier",
    "Serrurerie - Plateforme",
    "VSM (Value Stream Mapping)",
    "AGV",
]


def _slug(s: str) -> str:
    """Convertit un libellé en id de collection (minuscules, tirets)."""
    s = s.lower().strip()
    s = re.sub(r"[àâä]", "a", s)
    s = re.sub(r"[éèêë]", "e", s)
    s = re.sub(r"[îï]", "i", s)
    s = re.sub(r"[ôö]", "o", s)
    s = re.sub(r"[ùûü]", "u", s)
    s = re.sub(r"œ", "oe", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "default"


def category_to_collection_id(prefix: str, label: str) -> str:
    """Ex: ('contrainte', 'Contrainte sécurité') -> 'contrainte-securite'."""
    return f"{prefix}-{_slug(label)}"


# Liste de toutes les collections "catégorie" (pour les créer en batch)
def get_all_category_collection_specs() -> list[dict[str, str]]:
    """Retourne la liste des { name, id } pour chaque valeur de chaque taxonomie."""
    specs = []
    for label in FAMILLES_CONTRAINTE:
        cid = category_to_collection_id("contrainte", label)
        specs.append({"id": cid, "name": label, "type": "famille_contrainte"})
    for label in UNIVERS:
        cid = category_to_collection_id("univers", label)
        specs.append({"id": cid, "name": label, "type": "univers"})
    for label in SECTEURS_ACTIVITE:
        cid = category_to_collection_id("secteur", label)
        specs.append({"id": cid, "name": label, "type": "secteur_activite"})
    for label in DOMAINES_APPLICATION:
        cid = category_to_collection_id("domaine", label)
        specs.append({"id": cid, "name": label, "type": "domaine_application"})
    for label in LOTS:
        cid = category_to_collection_id("lot", label)
        specs.append({"id": cid, "name": label, "type": "lot"})
    return specs


def classify_document(text: str) -> dict[str, Any]:
    """
    Utilise l'IA pour classifier le document selon la taxonomie.
    Retourne les listes de libellés choisis parmi les listes officielles,
    plus les collection_id correspondants pour indexation.
    """
    if not text or not text.strip():
        return {
            "famille_contraintes": [],
            "univers": [],
            "secteur_activite": [],
            "domaine_application": [],
            "lots": [],
            "collection_ids": [],
            "raw_response": None,
        }

    text = text.strip()[:MAX_TEXT_LENGTH]
    familles_str = " | ".join(f'"{f}"' for f in FAMILLES_CONTRAINTE)
    univers_str = " | ".join(f'"{u}"' for u in UNIVERS)
    secteurs_str = " | ".join(f'"{s}"' for s in SECTEURS_ACTIVITE)
    domaines_str = " | ".join(f'"{d}"' for d in DOMAINES_APPLICATION)
    lots_str = " | ".join(f'"{l}"' for l in LOTS)

    system = """Tu es un expert en classification de documents techniques et industriels.
Tu dois analyser le document et choisir UNIQUEMENT parmi les listes fournies (recopie exactement les libellés).
Réponds en JSON valide uniquement, sans markdown ni texte autour, avec exactement ces clés :
- "famille_contraintes" : tableau de 0 à 3 libellés parmi la liste "Famille de contrainte"
- "univers" : tableau de 0 à 2 libellés parmi la liste "Univers"
- "secteur_activite" : une seule chaîne parmi "Secteur d'activité" (ou tableau d'un élément)
- "domaine_application" : tableau de 0 à 3 libellés parmi "Domaine d'application"
- "lots" : tableau de 0 à 5 libellés parmi la liste "Lots"

Si tu ne peux pas déterminer, utilise un tableau vide [] ou pour secteur une chaîne vide."""

    user = f"""Listes autorisées (choisis uniquement parmi celles-ci) :

Famille de contrainte : {familles_str}

Univers : {univers_str}

Secteur d'activité : {secteurs_str}

Domaine d'application : {domaines_str}

Lots : {lots_str}

---
Document à classifier :

{text}

---
Réponds uniquement par un objet JSON avec les clés famille_contraintes, univers, secteur_activite, domaine_application, lots."""

    client = get_client()
    response = client.chat.complete(
        model="open-mistral-7b",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    raw = (response.choices[0].message.content or "").strip()
    # Nettoyer un éventuel bloc markdown
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "famille_contraintes": [],
            "univers": [],
            "secteur_activite": [],
            "domaine_application": [],
            "lots": [],
            "collection_ids": [],
            "raw_response": raw,
        }

    famille_contraintes = _ensure_list(data.get("famille_contraintes"))
    univers = _ensure_list(data.get("univers"))
    secteur_activite = data.get("secteur_activite")
    if isinstance(secteur_activite, list):
        secteur_activite = secteur_activite[0] if secteur_activite else ""
    secteur_activite = secteur_activite or ""
    domaine_application = _ensure_list(data.get("domaine_application"))
    lots = _ensure_list(data.get("lots"))

    # Filtrer pour ne garder que les valeurs dans les listes officielles
    famille_contraintes = [f for f in famille_contraintes if f in FAMILLES_CONTRAINTE]
    univers = [u for u in univers if u in UNIVERS]
    if secteur_activite not in SECTEURS_ACTIVITE:
        secteur_activite = ""
    domaine_application = [d for d in domaine_application if d in DOMAINES_APPLICATION]
    lots = [l for l in lots if l in LOTS]

    collection_ids = []
    for f in famille_contraintes:
        collection_ids.append(category_to_collection_id("contrainte", f))
    for u in univers:
        collection_ids.append(category_to_collection_id("univers", u))
    if secteur_activite:
        collection_ids.append(category_to_collection_id("secteur", secteur_activite))
    for d in domaine_application:
        collection_ids.append(category_to_collection_id("domaine", d))
    for l in lots:
        collection_ids.append(category_to_collection_id("lot", l))

    return {
        "famille_contraintes": famille_contraintes,
        "univers": univers,
        "secteur_activite": secteur_activite,
        "domaine_application": domaine_application,
        "lots": lots,
        "collection_ids": collection_ids,
        "raw_response": raw,
    }


def _ensure_list(x: Any) -> list:
    if x is None:
        return []
    if isinstance(x, list):
        return list(x)
    return [x]


def extract_numero_affaire(text: str) -> str:
    """
    Utilise Mistral pour extraire le numéro d'affaire ou l'identifiant d'affaire du document.
    Retourne la chaîne extraite ou une chaîne vide si non trouvé.
    """
    if not text or not text.strip():
        return ""
    text = text.strip()[:MAX_TEXT_LENGTH]
    client = get_client()
    system = """Tu extrais uniquement le numéro d'affaire ou l'identifiant d'affaire mentionné dans le document (ex: 8888-24-0001, Affaire 123, n° affaire XXX).
Réponds par ce numéro ou identifiant seul, sans phrase. Si aucun numéro d'affaire n'est trouvé, réponds exactement: AUCUN"""
    user = f"Document:\n\n{text}\n\n---\nNuméro d'affaire (ou AUCUN):"
    response = client.chat.complete(
        model="open-mistral-7b",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    raw = (response.choices[0].message.content or "").strip()
    if not raw or raw.upper() == "AUCUN":
        return ""
    return raw.strip()
