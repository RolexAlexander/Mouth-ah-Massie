"""SQLite-backed Workspace — the structured shared state for a research project.

This replaces the `/tmp` markdown-file protocol with a typed, queryable,
restartable store. The Manager owns it; every other agent reads/writes
through workspace_tools.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional
from uuid import uuid4

from .config import CONFIG
from .schemas import (
    CritiqueScore,
    Finding,
    Plan,
    ProjectBrief,
    SubQuestion,
    SubQuestionStatus,
    WorkspaceSnapshot,
)

_DB_LOCK = threading.Lock()


def _connect() -> sqlite3.Connection:
    Path(CONFIG.workspace_db).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CONFIG.workspace_db, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db() -> None:
    with _DB_LOCK, _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                brief_json TEXT,
                plan_json TEXT,
                round_number INTEGER DEFAULT 0,
                report_draft TEXT,
                final_report TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                sub_question_id TEXT NOT NULL,
                round_number INTEGER NOT NULL,
                finding_json TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(project_id)
            );
            CREATE TABLE IF NOT EXISTS critiques (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                sub_question_id TEXT NOT NULL,
                round_number INTEGER NOT NULL,
                critique_json TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(project_id)
            );
            """
        )


@contextmanager
def _txn():
    with _DB_LOCK:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Project lifecycle
# ---------------------------------------------------------------------------
def create_project(brief: ProjectBrief) -> str:
    init_db()
    project_id = uuid4().hex[:12]
    with _txn() as conn:
        conn.execute(
            "INSERT INTO projects (project_id, brief_json) VALUES (?, ?)",
            (project_id, brief.model_dump_json()),
        )
    return project_id


def get_brief(project_id: str) -> Optional[ProjectBrief]:
    with _txn() as conn:
        row = conn.execute(
            "SELECT brief_json FROM projects WHERE project_id = ?", (project_id,)
        ).fetchone()
    if not row or not row["brief_json"]:
        return None
    return ProjectBrief.model_validate_json(row["brief_json"])


def set_plan(project_id: str, plan: Plan) -> None:
    with _txn() as conn:
        conn.execute(
            "UPDATE projects SET plan_json = ? WHERE project_id = ?",
            (plan.model_dump_json(), project_id),
        )


def get_plan(project_id: str) -> Optional[Plan]:
    with _txn() as conn:
        row = conn.execute(
            "SELECT plan_json FROM projects WHERE project_id = ?", (project_id,)
        ).fetchone()
    if not row or not row["plan_json"]:
        return None
    return Plan.model_validate_json(row["plan_json"])


def update_subquestion_status(project_id: str, sq_id: str, status: str) -> None:
    plan = get_plan(project_id)
    if not plan:
        return
    for sq in plan.sub_questions:
        if sq.id == sq_id:
            sq.status = status
            break
    set_plan(project_id, plan)


def increment_round(project_id: str) -> int:
    with _txn() as conn:
        conn.execute(
            "UPDATE projects SET round_number = round_number + 1 WHERE project_id = ?",
            (project_id,),
        )
        row = conn.execute(
            "SELECT round_number FROM projects WHERE project_id = ?", (project_id,)
        ).fetchone()
    return row["round_number"]


def get_round(project_id: str) -> int:
    with _txn() as conn:
        row = conn.execute(
            "SELECT round_number FROM projects WHERE project_id = ?", (project_id,)
        ).fetchone()
    return row["round_number"] if row else 0


# ---------------------------------------------------------------------------
# Findings & critiques
# ---------------------------------------------------------------------------
def add_finding(project_id: str, finding: Finding) -> None:
    round_num = get_round(project_id)
    with _txn() as conn:
        conn.execute(
            "INSERT INTO findings (project_id, sub_question_id, round_number, finding_json) "
            "VALUES (?, ?, ?, ?)",
            (project_id, finding.sub_question_id, round_num, finding.model_dump_json()),
        )
    update_subquestion_status(project_id, finding.sub_question_id, SubQuestionStatus.DONE)


def get_findings(project_id: str, sub_question_id: Optional[str] = None) -> list[Finding]:
    """Latest finding per sub-question (after critique loops, only the most recent matters)."""
    with _txn() as conn:
        if sub_question_id:
            rows = conn.execute(
                "SELECT finding_json FROM findings "
                "WHERE project_id = ? AND sub_question_id = ? "
                "ORDER BY id DESC",
                (project_id, sub_question_id),
            ).fetchall()
            return [Finding.model_validate_json(r["finding_json"]) for r in rows[:1]]

        # All sub-questions, latest finding for each
        rows = conn.execute(
            "SELECT finding_json FROM findings f1 "
            "WHERE project_id = ? AND id = ("
            "  SELECT MAX(id) FROM findings f2 "
            "  WHERE f2.project_id = f1.project_id "
            "  AND f2.sub_question_id = f1.sub_question_id"
            ")",
            (project_id,),
        ).fetchall()
    return [Finding.model_validate_json(r["finding_json"]) for r in rows]


def add_critique(project_id: str, critique: CritiqueScore) -> None:
    round_num = get_round(project_id)
    with _txn() as conn:
        conn.execute(
            "INSERT INTO critiques (project_id, sub_question_id, round_number, critique_json) "
            "VALUES (?, ?, ?, ?)",
            (project_id, critique.sub_question_id, round_num, critique.model_dump_json()),
        )
    if not critique.accept:
        update_subquestion_status(
            project_id, critique.sub_question_id, SubQuestionStatus.INSUFFICIENT
        )


def get_latest_critique(project_id: str, sq_id: str) -> Optional[CritiqueScore]:
    with _txn() as conn:
        row = conn.execute(
            "SELECT critique_json FROM critiques "
            "WHERE project_id = ? AND sub_question_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (project_id, sq_id),
        ).fetchone()
    return CritiqueScore.model_validate_json(row["critique_json"]) if row else None


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def set_report_draft(project_id: str, draft: str) -> None:
    with _txn() as conn:
        conn.execute(
            "UPDATE projects SET report_draft = ? WHERE project_id = ?",
            (draft, project_id),
        )


def set_final_report(project_id: str, report: str) -> None:
    with _txn() as conn:
        conn.execute(
            "UPDATE projects SET final_report = ? WHERE project_id = ?",
            (report, project_id),
        )


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------
def snapshot(project_id: str) -> WorkspaceSnapshot:
    with _txn() as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE project_id = ?", (project_id,)
        ).fetchone()
    if not row:
        raise ValueError(f"No project: {project_id}")

    brief = ProjectBrief.model_validate_json(row["brief_json"]) if row["brief_json"] else None
    plan = Plan.model_validate_json(row["plan_json"]) if row["plan_json"] else None
    findings = get_findings(project_id)

    with _txn() as conn:
        crit_rows = conn.execute(
            "SELECT critique_json FROM critiques c1 "
            "WHERE project_id = ? AND id = ("
            "  SELECT MAX(id) FROM critiques c2 "
            "  WHERE c2.project_id = c1.project_id "
            "  AND c2.sub_question_id = c1.sub_question_id"
            ")",
            (project_id,),
        ).fetchall()
    critiques = [CritiqueScore.model_validate_json(r["critique_json"]) for r in crit_rows]

    return WorkspaceSnapshot(
        project_id=project_id,
        brief=brief,
        plan=plan,
        findings=findings,
        critiques=critiques,
        round_number=row["round_number"] or 0,
        report_draft=row["report_draft"],
        final_report=row["final_report"],
    )
