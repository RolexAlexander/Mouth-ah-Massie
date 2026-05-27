"""Researcher agent — answers ONE sub-question with web search + page reads."""
from google.adk.agents.llm_agent import Agent

from deep_research.config import CONFIG
from deep_research.prompts import RESEARCHER_PROMPT
from tools.search_tools import read_page, web_search
from tools.workspace_tools import get_plan, save_finding


researcher_agent = Agent(
    model=CONFIG.model_researcher,
    name="researcher",
    description=(
        "Answers a single sub-question by searching the web and reading pages. "
        "Saves a structured Finding (answer, key facts, sources with tier, "
        "confidence, open questions) to the workspace. The Manager delegates "
        "one sub_question_id at a time."
    ),
    instruction=RESEARCHER_PROMPT,
    tools=[get_plan, web_search, read_page, save_finding],
)
