from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mistral_api_key: str = ""
    chroma_data_path: str = "./data/chroma"
    log_level: str = "INFO"
    max_file_size_mb: int = 50
    max_audio_size_mb: int = 100
    transcription_model: str = "voxtral-mini-latest"
    allowed_origins: str = "*"
    chunk_size: int = 512
    chunk_overlap: int = 128
    # Authentification interface (si vides, pas d'auth)
    interface_code: str = "AnthonyWendlingAPIMistral"
    interface_password: str = "&RlHB17oXIUcr&"
    interface_secret_key: str = "change-me-in-production"


settings = Settings()
