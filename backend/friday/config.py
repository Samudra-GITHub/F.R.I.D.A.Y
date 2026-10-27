"""Application configuration and security defaults for F.R.I.D.A.Y."""

import os
from pathlib import Path
from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Central settings for F.R.I.D.A.Y. Milestone 1."""
    app_name: str = "F.R.I.D.A.Y."
    version: str = "0.1.0"
    
    # Strictly localhost binding — never expose to 0.0.0.0 / local network
    host: str = "127.0.0.1"
    port: int = 8000
    
    # Ollama endpoint and local model selection
    ollama_base_url: str = "http://127.0.0.1:11434"
    model_name: str = "qwen2.5:7b"
    request_timeout_seconds: float = 60.0
    
    # Configurable workspace root (must resolve to an absolute path)
    workspace_root: Path = Field(
        default_factory=lambda: Path(
            os.environ.get("FRIDAY_WORKSPACE", str(Path.home() / "FridayWorkspace"))
        ).resolve()
    )
    max_workspace_entries: int = 40
    
    # Media control policy: disabled by default in Milestone 1
    media_control_enabled: bool = False
    
    # Execution & reasoning budget limits
    max_turns_per_request: int = 6
    max_tool_calls_per_turn: int = 8


# Global settings instance
settings = Settings()
