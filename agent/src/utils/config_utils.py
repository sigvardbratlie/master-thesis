from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from pathlib import Path
import tomllib

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

class AsyncConfig(BaseModel):
    max_concurrent_requests: int = 20
    throttle_value: float = 0.0



class ModelProviderConfig(BaseModel):
    base_url: str = ""
    max_tokens: int = 4096

class ModelsConfig(BaseModel):
    together: ModelProviderConfig = Field(default_factory=ModelProviderConfig)

class AgentStream(BaseModel):
    max_token_tool: int = 10000
    sum_rate : int = 20

    #related to the factsheet in agent
    use_factsheet: bool = True
    significance : list[str] = ["high", "medium", "low"]  
    embed_to_vectorstore: bool = True
    save_to_storage: bool = True
    minimal_context: bool = False


class ProjectConfig(BaseModel):
    threshold: int = 5120000     # 500 * 1024
    max_attachments: int = 10
    max_emails: int = 15
    embed_to_vectorstore: bool = True
    save_to_storage: bool = True
    

# 2. Definer hovedkonfigurasjonen som BaseSettings
class AppConfig(BaseSettings):
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    async_tasks: AsyncConfig = Field(default_factory=AsyncConfig, alias="async") 
    agent: AgentStream = Field(default_factory=AgentStream)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    project : ProjectConfig = Field(default_factory=ProjectConfig)


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