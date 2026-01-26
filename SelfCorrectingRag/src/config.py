"""
Configuration module for Self-Correcting Codeforces Tutor.
Loads settings from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass, field
from typing import Literal
from dotenv import load_dotenv

load_dotenv()


@dataclass
class AlfaConfig:
    """Alfa LLM proxy configuration."""
    claim: str = field(default_factory=lambda: os.getenv("ALFA_CLAIM", ""))
    env: str = field(default_factory=lambda: os.getenv("ALFA_ENV", "qa"))
    
    @property
    def base_url(self) -> str:
        return f"http://alfa.gamma.{self.env}.us-west-2.aws.<company>.io"
    
    @property
    def api_key(self) -> str:
        return f"sk-{self.claim}"


@dataclass
class ExecutionConfig:
    """Code execution settings."""
    timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("CODE_TIMEOUT_SECONDS", "5"))
    )
    max_repair_iterations: int = field(
        default_factory=lambda: int(os.getenv("MAX_REPAIR_ITERATIONS", "5"))
    )
    stress_test_count: int = field(
        default_factory=lambda: int(os.getenv("STRESS_TEST_COUNT", "100"))
    )


@dataclass
class Config:
    """Main configuration container."""
    alfa: AlfaConfig = field(default_factory=AlfaConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    default_model: str = field(
        default_factory=lambda: os.getenv("DEFAULT_MODEL", "claude-4-sonnet")
    )
    
    # Available models
    AVAILABLE_MODELS: tuple = ("claude-4-sonnet", "gpt-5")
    
    def validate(self) -> None:
        """Validate configuration."""
        if not self.alfa.claim:
            raise ValueError("ALFA_CLAIM environment variable is required")
        if self.default_model not in self.AVAILABLE_MODELS:
            raise ValueError(
                f"Invalid model: {self.default_model}. "
                f"Available: {self.AVAILABLE_MODELS}"
            )


# Global config instance
config = Config()

