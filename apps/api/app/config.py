from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_env: str = "development"
    log_level: str = "DEBUG"
    allowed_origins: str = "http://localhost:3000"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/openclaw"

    # Auth (JWT)
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 60
    algorithm: str = "HS256"

    # SSO — OAuth2 / OIDC providers
    # Set the base URL that providers redirect back to (must match provider console setting)
    sso_redirect_base_url: str = "http://localhost:8000"
    # Google OAuth2 — https://console.cloud.google.com/apis/credentials
    google_client_id: str = ""
    google_client_secret: str = ""
    # GitHub OAuth App — https://github.com/settings/developers
    github_client_id: str = ""
    github_client_secret: str = ""
    # Microsoft / Entra ID — https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_tenant_id: str = "common"  # "common" = multi-tenant; set to org tenant for single-tenant

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Telegram
    telegram_webhook_base_url: str = "https://your-domain.com/api/connectors/telegram"

    # Email defaults (per-account creds stored via credentials_ref)
    smtp_host: str = ""
    smtp_port: int = 587
    imap_host: str = ""
    imap_port: int = 993

    # Vault / KMS
    vault_addr: str = "http://localhost:8200"
    vault_token: str = ""

    # Encryption key for API keys stored in DB (Fernet — see services/secrets.py)
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Must be the same value across all API + orchestrator instances.
    encryption_key: str = "change-me-generate-a-real-fernet-key"

    # Docker / Container Management
    # The Docker network agents are spawned onto (agent-net only — never backend-net).
    # Format: {compose_project_name}_{network_name}
    # Override if your project dir name differs from "agent-orchestrator".
    docker_agent_network: str = "agent-orchestrator_agent-net"
    docker_agent_image: str = "openclaw/agent-runtime:latest"
    # Set to "unix:///var/run/docker.sock" or "tcp://..." for remote Docker daemon
    docker_host: str = ""   # empty = use DOCKER_HOST env var or default socket

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


settings = Settings()
