"""Writer agent — produces the final two-layer report."""
from google.adk.agents.llm_agent import Agent

from deep_research.config import CONFIG
from deep_research.prompts import WRITER_PROMPT
from tools.workspace_tools import (
    get_workspace_snapshot,
    save_final_report,
    save_report_draft,
)


writer_agent = Agent(
    model=CONFIG.model_writer,
    name="writer",
    description=(
        "Reads the full workspace and produces the final two-layer report "
        "(Evidence Layer + Interpretation Layer + Limitations + Sources). "
        "If evidence is insufficient, can flag gaps back to the Manager "
        "instead of writing a weak report."
    ),
    instruction=WRITER_PROMPT,
    tools=[get_workspace_snapshot, save_report_draft, save_final_report],
)
