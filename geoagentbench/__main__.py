"""CLI entry point: python -m geoagentbench"""

import sys
from pathlib import Path

# Make the bundled API package importable as a top-level path so the agent
# module (``api/agent``) can be imported as ``agent.*``. The runner does
# ``from agent.agent import run_agent`` and the agent code itself uses
# ``from cache_manager import ...`` style; both work once ``api/`` is on
# sys.path. This is a no-op if the user has set up their own PYTHONPATH.
_API_DIR = Path(__file__).resolve().parent.parent / "api"
if _API_DIR.is_dir() and str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

from geoagentbench.runner import main  # noqa: E402

if __name__ == "__main__":
    main()
