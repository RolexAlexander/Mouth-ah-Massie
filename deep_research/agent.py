"""Entry point for `adk run deep_research` and `adk web`.

ADK looks for a `root_agent` variable in this module.
"""
from deep_research.agents.manager import manager_agent
from deep_research.workspace import init_db


# Initialize the SQLite workspace DB on import so the first call doesn't race.
init_db()

# The name ADK looks for.
root_agent = manager_agent
