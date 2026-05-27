"""Typed schemas for the structured workspace.

These are the contract between agents. No agent ever passes free-form
markdown to another agent — only structured objects that go through here.
"""
from __future__ import annotations

from datetime import datetime
from enum import IntEnum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class SourceTier(IntEnum):
    """Source quality tiers. Lower is better.

    Used by the Critic to flag findings that rest on weak evidence, and by the
    Writer to surface confidence markers on claims.
    """

    PEER_REVIEWED = 1   # academic journals, books, .edu papers
    OFFICIAL = 2        # government, regulatory, court records, official statistics
    MAJOR_NEWS = 3      # reputable established news outlets
    INDUSTRY = 4        # company blogs, industry analyst reports, trade press
    UNVERIFIED = 5      # forums, social media, personal blogs, unknown


class SubQuestionStatus(str):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    INSUFFICIENT = "insufficient"  # critic rejected, needs another pass


class SubQuestion(BaseModel):
    """A single sub-question the Planner produced. Researchers consume these."""

    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    question: str
    rationale: str = Field(description="Why this question matters for the brief.")
    expected_source_types: list[str] = Field(
        default_factory=list,
        description="What kinds of sources should answer this (e.g. 'court rulings', 'BoG statistics', 'analyst reports').",
    )
    priority: int = Field(default=2, description="1=critical, 2=normal, 3=nice-to-have")
    status: str = Field(default=SubQuestionStatus.PENDING)


class Source(BaseModel):
    """A single source consulted by a Researcher."""

    url: str
    title: str = ""
    tier: SourceTier = SourceTier.UNVERIFIED
    excerpt: str = Field(default="", description="The specific passage that supports the finding.")


class Finding(BaseModel):
    """A Researcher's structured answer to one sub-question.

    This replaces the markdown-dump pattern. Critics score this; Writer reads it.
    """

    sub_question_id: str
    answer: str = Field(description="Concise direct answer to the sub-question.")
    key_facts: list[str] = Field(
        default_factory=list,
        description="Atomic factual claims, each backed by at least one source in `sources`.",
    )
    sources: list[Source] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    open_questions: list[str] = Field(
        default_factory=list,
        description="Unresolved threads the Researcher noticed but couldn't close.",
    )
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class CritiqueScore(BaseModel):
    """Critic's verdict on a Finding."""

    sub_question_id: str
    score: float = Field(ge=0.0, le=1.0, description="Overall quality score.")
    answers_question: bool
    sufficient_sources: bool
    source_tier_ok: bool
    issues: list[str] = Field(default_factory=list, description="Specific things wrong.")
    accept: bool = Field(description="True if Manager can move on; False triggers re-research.")


class Plan(BaseModel):
    """The Planner's output."""

    brief_restated: str
    objectives: list[str]
    sub_questions: list[SubQuestion]
    success_criteria: list[str] = Field(
        description="What 'done' looks like for the whole project. The Manager checks against this."
    )


class ProjectBrief(BaseModel):
    """What the Manager extracts from the initial user request."""

    title: str
    research_question: str
    audience: str = Field(default="general analyst", description="Who is the report for?")
    desired_depth: str = Field(default="standard", description="quick / standard / exhaustive")
    constraints: list[str] = Field(default_factory=list)
    private_corpus_paths: list[str] = Field(
        default_factory=list,
        description="Paths/identifiers for private docs to include alongside web sources.",
    )


class WorkspaceSnapshot(BaseModel):
    """Read-only view of the full workspace state at a point in time."""

    project_id: str
    brief: Optional[ProjectBrief] = None
    plan: Optional[Plan] = None
    findings: list[Finding] = Field(default_factory=list)
    critiques: list[CritiqueScore] = Field(default_factory=list)
    round_number: int = 0
    report_draft: Optional[str] = None
    final_report: Optional[str] = None
