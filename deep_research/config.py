"""Central configuration. All knobs read from .env with sane defaults."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root if it exists
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Config:
    # Models
    model_manager: str = os.getenv("DR_MODEL_MANAGER", "gemini-2.5-pro")
    model_planner: str = os.getenv("DR_MODEL_PLANNER", "gemini-2.5-pro")
    model_writer: str = os.getenv("DR_MODEL_WRITER", "gemini-2.5-pro")
    model_critic: str = os.getenv("DR_MODEL_CRITIC", "gemini-2.5-flash")
    model_researcher: str = os.getenv("DR_MODEL_RESEARCHER", "gemini-2.5-flash")

    # Search
    searxng_base_url: str = os.getenv("SEARXNG_BASE_URL", "http://localhost:8081")

    # Budgets
    max_subquestions: int = int(os.getenv("DR_MAX_SUBQUESTIONS", "8"))
    max_research_rounds: int = int(os.getenv("DR_MAX_RESEARCH_ROUNDS", "3"))
    max_parallel_researchers: int = int(os.getenv("DR_MAX_PARALLEL_RESEARCHERS", "4"))
    max_searches_per_subquestion: int = int(os.getenv("DR_MAX_SEARCHES_PER_SUBQUESTION", "6"))
    min_sources_per_subquestion: int = int(os.getenv("DR_MIN_SOURCES_PER_SUBQUESTION", "2"))
    min_source_tier: int = int(os.getenv("DR_MIN_SOURCE_TIER", "3"))

    # Storage
    workspace_db: str = os.getenv("DR_WORKSPACE_DB", "./dr_workspace.db")


CONFIG = Config()
