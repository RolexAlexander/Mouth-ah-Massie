"""Manager agent — the root orchestrator.

Owns the workspace, applies the termination rubric, and delegates to the
specialist agents. Strong model — this is where the hard cognitive work
of the system lives (decomposition decisions, gap detection, when-to-stop).
"""
from google.adk.agents.llm_agent import Agent
from google.adk.tools.agent_tool import AgentTool

from deep_research.agents.critic import critic_agent
from deep_research.agents.planner import planner_agent
from deep_research.agents.researcher import researcher_agent
from deep_research.agents.writer import writer_agent
from deep_research.config import CONFIG
from deep_research.prompts import MANAGER_PROMPT
from tools.workspace_tools import (
    create_project,
    get_brief,
    get_open_subquestions,
    get_workspace_snapshot,
    increment_round,
)


# We expose sub-agents as AgentTools so the Manager can call them like
# regular tools (one at a time, with arguments). This is the pattern that
# avoids the "free-text path passing" fragility you had in your original
# Goose ADK system.
manager_agent = Agent(
    model=CONFIG.model_manager,
    name="manager",
    description=(
        "Research project manager. Orchestrates the planner, researchers, "
        "critic, and writer to produce a fully-cited research report. "
        "Owns the workspace and the termination rubric."
    ),
    instruction=MANAGER_PROMPT,
    tools=[
        # Workspace ops the Manager needs directly
        create_project,
        get_brief,
        get_open_subquestions,
        get_workspace_snapshot,
        increment_round,
        # Sub-agents as callable tools
        AgentTool(agent=planner_agent),
        AgentTool(agent=researcher_agent),
        AgentTool(agent=critic_agent),
        AgentTool(agent=writer_agent),
    ],
)
