from functools import lru_cache
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings
from pathlib import Path
import tomllib
import logging

logger = logging.getLogger(__name__)

# 1. Definer de indre blokkene som BaseModel
class FileLoggingConfig(BaseModel):
    enabled: bool = False
    level: str = "info"
    path: str = "logs/app.log"

class ConsoleLoggingConfig(BaseModel):
    enabled: bool = True
    level: str = "info"

class LoggingConfig(BaseModel):
    level: str = "info"
    file: FileLoggingConfig = Field(default_factory=FileLoggingConfig)
    console: ConsoleLoggingConfig = Field(default_factory=ConsoleLoggingConfig)

class AsyncBaseConfig(BaseModel):
    max_concurrent_requests: int = 5
    throttle_value: float = 0.0
    requests_per_second: float | None = None  # rate limiter (LLM only)
    max_burst_size: int = 10                  # token bucket burst capacity (LLM only)
    retry_attempts: int = 0                   # with_retry stop_after_attempt (LLM only, 0 = disabled)
    retry_wait_min: float = 30.0              # min seconds to wait on 429 (astream retry, LLM only)
    retry_wait_max: float = 120.0             # max seconds to wait on 429 (astream retry, LLM only)

class AsyncConfig(BaseModel):
    llm: AsyncBaseConfig = Field(default_factory=AsyncBaseConfig)
    vectorstore: AsyncBaseConfig = Field(default_factory=AsyncBaseConfig)
    storage: AsyncBaseConfig = Field(default_factory=AsyncBaseConfig)
    database: AsyncBaseConfig = Field(default_factory=AsyncBaseConfig)

class ModelProviderConfig(BaseModel):
    base_url: str = ""
    max_tokens: int = 4096

class ModelsConfig(BaseModel):
    together: ModelProviderConfig = Field(default_factory=ModelProviderConfig)

class AgentConfig(BaseModel):
    max_token_tool: int | None = None
    sum_rate : int = 20
    context_window : int = 250000

    #related to the factsheet in agent
    use_factsheet: bool = True
    significance : list[str] = ["high", "medium", "low"]  
    embed_to_vectorstore: bool = True
    save_to_storage: bool = True
    minimal_context: bool = False
    prompt_file_path : str = "system_prompt.txt"

    @model_validator(mode="after")
    def enforce_minimal_context(self):
        if self.minimal_context:
            logger.warning("⚠️  Minimal context is enabled. This will override significance to only include 'high'.")
            self.significance = ["high"]
        return self

class StorageAWSConfig(BaseModel):
    bucket_name: str = ""
    region: str = ""

class StorageGCSConfig(BaseModel):
    bucket_name: str = ""
    region_name : str = ""

class StorageSupabaseConfig(BaseModel):
    bucket_name: str = ""


class StorageConfig(BaseModel):
    max_concurrent_uploads: int = 1
    max_retries: int = 3
    aws: StorageAWSConfig = Field(default_factory=StorageAWSConfig)
    gcs: StorageGCSConfig = Field(default_factory=StorageGCSConfig)
    supabase: StorageSupabaseConfig = Field(default_factory=StorageSupabaseConfig)

class ProjectCleanConfig(BaseModel):
    chunk_size : int = 200

class ProjectConfig(BaseModel):
    size_threshold: int = 5120000     # 500 * 1024
    token_threshold: int = 128000
    max_attachments: int = 10
    max_emails: int = 15
    embed_to_vectorstore: bool = True
    save_to_storage: bool = True
    clean : ProjectCleanConfig = Field(default_factory=ProjectCleanConfig)
    
class VectorstoreBQConfig(BaseModel):
    embedding_model: str = "google_gemini-embedding-001"
    region : str
    dataset : str

class VectorstoreConfig(BaseModel):
    chunk_size: int = 1000
    chunk_overlap: int = 200
    k : int = 3
    bigquery : VectorstoreBQConfig = Field(default_factory=VectorstoreBQConfig)

# ========= MAIN CONFIG CLASS =========
class AppConfig(BaseSettings):
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    async_tasks: AsyncConfig = Field(default_factory=AsyncConfig, alias="async") 
    agent: AgentConfig = Field(default_factory=AgentConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    project : ProjectConfig = Field(default_factory=ProjectConfig)
    vectorstore : VectorstoreConfig = Field(default_factory=VectorstoreConfig)
    storage : StorageConfig = Field(default_factory=StorageConfig)


    @classmethod
    def from_toml(cls, path: str | Path) -> "AppConfig":
        """Loads and validates config from a TOML file."""
        file_path = Path(path)
        
        if not file_path.exists():
            print(f"⚠️ Warning: No configfile at location {path}, using default values.")
            return cls()

        with open(file_path, "rb") as f:
            config_dict = tomllib.load(f)

        return cls(**config_dict)


@lru_cache
def get_app_config() -> AppConfig:
    """Returns the singleton AppConfig, loaded from agent/config.toml."""
    config_path = Path(__file__).resolve().parent.parent.parent / "config.toml"
    return AppConfig.from_toml(config_path)