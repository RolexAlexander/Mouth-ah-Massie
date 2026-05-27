"""Local CLI runner for the Deep Research system.

Usage:
    python run_local.py "Your research question here"
    python run_local.py --file question.txt
    python run_local.py --inspect <project_id>   # view a past project's workspace

This uses ADK's Runner + InMemorySessionService for a single-shot run.
For an interactive UI, run `adk web` from the project root instead.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from deep_research.agent import root_agent
from deep_research.workspace import init_db, snapshot

console = Console()


async def run_research(question: str) -> None:
    """Run a single research session end-to-end."""
    init_db()

    session_service = InMemorySessionService()
    app_name = "deep_research_adk"
    user_id = "local_user"
    session = await session_service.create_session(app_name=app_name, user_id=user_id)

    runner = Runner(
        agent=root_agent,
        app_name=app_name,
        session_service=session_service,
    )

    console.print(Panel.fit(
        f"[bold]Research question:[/bold]\n{question}",
        title="Starting research",
        border_style="cyan",
    ))

    content = types.Content(role="user", parts=[types.Part(text=question)])

    console.print("[dim](waiting for first model response — Gemini cold-start can take 30-60s)[/dim]")

    final_text = ""
    async for event in runner.run_async(
        user_id=user_id, session_id=session.id, new_message=content
    ):
        if event.is_final_response() and event.content and event.content.parts:
            text = event.content.parts[0].text or ""
            final_text = text
        # Stream intermediate signals to the console
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.function_call:
                    console.print(
                        f"[dim]→ {event.author} calls {part.function_call.name}"
                        f"({_short(part.function_call.args)})[/dim]"
                    )
                elif part.function_response:
                    resp = part.function_response.response
                    preview = _clip(str(resp)) if resp else ""
                    console.print(
                        f"[dim]← {part.function_response.name} returned {preview}[/dim]"
                    )
                elif part.text:
                    console.print(f"[dim italic]{event.author}: {_clip(part.text)}[/dim italic]")

    console.print(Panel(
        Markdown(final_text or "(no text returned)"),
        title="Manager's final message",
        border_style="green",
    ))


def _short(args) -> str:
    """Truncate tool-call args for readable streaming output."""
    if not args:
        return ""
    s = ", ".join(f"{k}={_clip(v)}" for k, v in args.items())
    return s if len(s) < 120 else s[:117] + "..."


def _clip(v) -> str:
    s = str(v)
    return s if len(s) < 60 else s[:57] + "..."


def inspect(project_id: str) -> None:
    init_db()
    try:
        snap = snapshot(project_id)
    except ValueError:
        console.print(f"[red]No project found with id {project_id}[/red]")
        return

    console.print(Panel.fit(f"Project: {snap.project_id}", border_style="cyan"))
    if snap.brief:
        console.print(f"[bold]Title:[/bold] {snap.brief.title}")
        console.print(f"[bold]Question:[/bold] {snap.brief.research_question}")
    console.print(f"[bold]Round:[/bold] {snap.round_number}")
    console.print(f"[bold]Findings:[/bold] {len(snap.findings)}")
    console.print(f"[bold]Critiques:[/bold] {len(snap.critiques)}")

    if snap.final_report:
        console.print(Panel(
            Markdown(snap.final_report),
            title="Final report",
            border_style="green",
        ))
    elif snap.report_draft:
        console.print(Panel(
            Markdown(snap.report_draft),
            title="Draft (not finalized)",
            border_style="yellow",
        ))


def main() -> None:
    parser = argparse.ArgumentParser(description="Deep Research ADK runner")
    parser.add_argument("question", nargs="?", help="Research question")
    parser.add_argument("--file", help="Read question from a text file")
    parser.add_argument("--inspect", help="Inspect a past project by ID")
    args = parser.parse_args()

    if args.inspect:
        inspect(args.inspect)
        return

    question = args.question
    if args.file:
        question = Path(args.file).read_text(encoding="utf-8").strip()

    if not question:
        parser.print_help()
        sys.exit(1)

    asyncio.run(run_research(question))


if __name__ == "__main__":
    main()
