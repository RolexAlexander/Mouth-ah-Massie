"""Workspace tools exposed to ADK agents.

These wrap the typed Workspace API so an LLM agent can read/write project
state through normal tool calls instead of free-text file passing.

Every function takes `project_id` as its first arg. The Manager extracts
the project_id from the brief on session start and the orchestration code
passes it along to sub-agents through ADK's session state.
"""
from __future__ import annotations

import json
from typing import Optional

from deep_research import workspace
from deep_research.schemas import (
    CritiqueScore,
    Finding,
    Plan,
    ProjectBrief,
    Source,
    SourceTier,
    SubQuestion,
    WorkspaceSnapshot,
)
from deep_research.source_quality import classify_url


# ---------------------------------------------------------------------------
# Project / brief
# ---------------------------------------------------------------------------
def create_project(
    title: str,
    research_question: str,
    audience: str = "general analyst",
    desired_depth: str = "standard",
    constraints: Optional[list[str]] = None,
) -> dict:
    """Create a new research project. Manager calls this once at session start.

    Args:
        title: Short project name.
        research_question: The core question to answer.
        audience: Who the final report is for.
        desired_depth: 'quick' | 'standard' | 'exhaustive'.
        constraints: Any specific limits or focus areas.

    Returns:
        {'project_id': str}
    """
    brief = ProjectBrief(
        title=title,
        research_question=research_question,
        audience=audience,
        desired_depth=desired_depth,
        constraints=constraints or [],
    )
    pid = workspace.create_project(brief)
    return {"project_id": pid}


def get_brief(project_id: str) -> dict:
    """Get the project brief.

    Args:
        project_id: The project ID.
    """
    b = workspace.get_brief(project_id)
    return b.model_dump() if b else {}


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------
def save_plan(
    project_id: str,
    brief_restated: str,
    objectives: list[str],
    sub_questions: list[dict],
    success_criteria: list[str],
) -> dict:
    """Save the research plan produced by the Planner.

    Args:
        project_id: Project ID.
        brief_restated: Planner's restatement of the brief in their own words.
        objectives: List of high-level objectives.
        sub_questions: List of dicts each with keys: 'question', 'rationale',
            'expected_source_types' (list of str), 'priority' (1-3).
        success_criteria: What 'done' looks like for the project.

    Returns:
        {'sub_question_ids': [...]} - the assigned IDs the Researcher will use.
    """
    sqs = [
        SubQuestion(
            question=sq["question"],
            rationale=sq.get("rationale", ""),
            expected_source_types=sq.get("expected_source_types", []),
            priority=sq.get("priority", 2),
        )
        for sq in sub_questions
    ]
    plan = Plan(
        brief_restated=brief_restated,
        objectives=objectives,
        sub_questions=sqs,
        success_criteria=success_criteria,
    )
    workspace.set_plan(project_id, plan)
    return {"sub_question_ids": [sq.id for sq in sqs]}


def get_plan(project_id: str) -> dict:
    """Get the current research plan.

    Args:
        project_id: Project ID.
    """
    p = workspace.get_plan(project_id)
    return p.model_dump() if p else {}


def get_open_subquestions(project_id: str) -> list[dict]:
    """Get sub-questions that still need work (pending or insufficient).

    Args:
        project_id: Project ID.
    """
    plan = workspace.get_plan(project_id)
    if not plan:
        return []
    return [
        sq.model_dump()
        for sq in plan.sub_questions
        if sq.status in ("pending", "insufficient")
    ]


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------
def save_finding(
    project_id: str,
    sub_question_id: str,
    answer: str,
    key_facts: list[str],
    sources: list[dict],
    confidence: float = 0.6,
    open_questions: Optional[list[str]] = None,
) -> dict:
    """Save a Researcher's finding for one sub-question.

    Source tier is auto-classified from the URL — Researcher does not need
    to guess it.

    Args:
        project_id: Project ID.
        sub_question_id: ID of the sub-question being answered.
        answer: Direct concise answer.
        key_facts: List of atomic factual claims.
        sources: List of dicts: 'url', 'title' (optional), 'excerpt' (optional).
        confidence: 0.0-1.0 self-assessed confidence.
        open_questions: Unresolved threads to flag for follow-up.

    Returns:
        {'status': 'saved', 'auto_tier_summary': {...}}
    """
    structured_sources: list[Source] = []
    tier_summary: dict[str, int] = {}
    for s in sources:
        url = s.get("url", "")
        tier = classify_url(url)
        structured_sources.append(
            Source(
                url=url,
                title=s.get("title", ""),
                tier=tier,
                excerpt=s.get("excerpt", ""),
            )
        )
        tier_summary[tier.name] = tier_summary.get(tier.name, 0) + 1

    finding = Finding(
        sub_question_id=sub_question_id,
        answer=answer,
        key_facts=key_facts,
        sources=structured_sources,
        confidence=confidence,
        open_questions=open_questions or [],
    )
    workspace.add_finding(project_id, finding)
    return {"status": "saved", "auto_tier_summary": tier_summary}


def get_findings(project_id: str) -> list[dict]:
    """Get all latest findings for the project.

    Args:
        project_id: Project ID.
    """
    return [f.model_dump() for f in workspace.get_findings(project_id)]


def get_finding(project_id: str, sub_question_id: str) -> dict:
    """Get the latest finding for a specific sub-question.

    Args:
        project_id: Project ID.
        sub_question_id: The sub-question ID.
    """
    fs = workspace.get_findings(project_id, sub_question_id)
    return fs[0].model_dump() if fs else {}


# ---------------------------------------------------------------------------
# Critique
# ---------------------------------------------------------------------------
def save_critique(
    project_id: str,
    sub_question_id: str,
    score: float,
    answers_question: bool,
    sufficient_sources: bool,
    source_tier_ok: bool,
    issues: list[str],
    accept: bool,
) -> dict:
    """Save a Critic's verdict on a Finding.

    Args:
        project_id: Project ID.
        sub_question_id: Sub-question being critiqued.
        score: 0.0-1.0 overall quality.
        answers_question: True if the finding actually addresses the sub-question.
        sufficient_sources: True if there are enough sources.
        source_tier_ok: True if sources meet quality bar.
        issues: List of specific problems if any.
        accept: True if Manager can move on, False to trigger re-research.
    """
    crit = CritiqueScore(
        sub_question_id=sub_question_id,
        score=score,
        answers_question=answers_question,
        sufficient_sources=sufficient_sources,
        source_tier_ok=source_tier_ok,
        issues=issues,
        accept=accept,
    )
    workspace.add_critique(project_id, crit)
    return {"status": "saved", "accept": accept}


# ---------------------------------------------------------------------------
# Rounds
# ---------------------------------------------------------------------------
def increment_round(project_id: str) -> dict:
    """Bump the round counter. Manager calls this before each research pass.

    Args:
        project_id: Project ID.
    """
    new_round = workspace.increment_round(project_id)
    return {"round_number": new_round}


def get_workspace_snapshot(project_id: str) -> dict:
    """Get the entire workspace state as a single snapshot.

    Manager and Writer use this for orchestration decisions and final synthesis.

    Args:
        project_id: Project ID.
    """
    snap = workspace.snapshot(project_id)
    return snap.model_dump()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def save_report_draft(project_id: str, draft: str) -> dict:
    """Save a draft of the report. Writer uses this for iteration.

    Args:
        project_id: Project ID.
        draft: Markdown draft text.
    """
    workspace.set_report_draft(project_id, draft)
    return {"status": "saved", "length": len(draft)}


def save_final_report(project_id: str, report: str) -> dict:
    """Save the final report. Writer calls this when done.

    Args:
        project_id: Project ID.
        report: Final markdown report.
    """
    workspace.set_final_report(project_id, report)
    return {"status": "saved", "length": len(report)}
