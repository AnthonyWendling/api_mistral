"""
Schémas pour la gestion des connexions API (sources) : NocoDB, etc.
Permet de configurer une table NocoDB et les endpoints pour indexer les documents.
"""
from pydantic import BaseModel, Field


class NocoDBConfig(BaseModel):
    """Configuration pour une source NocoDB (table de documents)."""
    base_url: str = Field(..., description="URL de l'API NocoDB (ex. https://xxx.nocodb.com)")
    api_key: str = Field("", description="Token API NocoDB (xc-token)")
    base_id: str = Field("", description="ID de la base NocoDB (optionnel)")
    table_id: str = Field(..., description="ID de la table (ex. mx_abc123)")
    collection_id: str = Field(
        ...,
        description="ID de collection fixe ou template (ex. nocodb-affaire-{{affaire_id}})",
    )
    field_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping champ NocoDB → paramètre indexation (file_url, document_id, nocodb_record_id, affaire_id, numero_affaire, etc.)",
    )
    limit: int = Field(100, ge=1, le=500, description="Nombre max d'enregistrements à récupérer par sync")


class SourceCreate(BaseModel):
    """Création d'une connexion API (source)."""
    name: str = Field(..., min_length=1, description="Nom de la connexion")
    type: str = Field("nocodb", description="Type de source (nocodb, ...)")
    enabled: bool = True
    config: dict = Field(default_factory=dict, description="Config selon le type (NocoDB: base_url, api_key, table_id, collection_id, field_mapping)")


class SourceUpdate(BaseModel):
    """Mise à jour partielle d'une source."""
    name: str | None = None
    enabled: bool | None = None
    config: dict | None = None


class SourceOut(BaseModel):
    """Source telle que retournée par l'API (sans exposer la clé API en clair)."""
    id: str
    name: str
    type: str
    enabled: bool
    config: dict
