"""Critic agent — scores Findings against the rubric."""
from google.adk.agents.llm_agent import Agent

from deep_research.config import CONFIG
from deep_research.prompts import CRITIC_PROMPT
from tools.workspace_tools import get_finding, get_plan, save_critique


critic_agent = Agent(
    model=CONFIG.model_critic,
    name="critic",
    description=(
        "Scores a single Finding against the rubric (answers the question, "
        "enough sources, source tiers acceptable). Cheap and fast — runs on "
        "every Finding. Manager delegates after each Researcher returns."
    ),
    instruction=CRITIC_PROMPT,
    tools=[get_plan, get_finding, save_critique],
)
