"""Planner agent — decomposes brief into typed sub-questions."""
from google.adk.agents.llm_agent import Agent

from deep_research.config import CONFIG
from deep_research.prompts import PLANNER_PROMPT
from tools.workspace_tools import get_brief, get_plan, save_plan


planner_agent = Agent(
    model=CONFIG.model_planner,
    name="planner",
    description=(
        "Decomposes a research brief into a typed plan with sub-questions, "
        "rationales, expected source types, and success criteria. Writes the "
        "plan to the workspace. Manager delegates here at the start and "
        "whenever the plan needs revision."
    ),
    instruction=PLANNER_PROMPT,
    tools=[get_brief, get_plan, save_plan],
)
