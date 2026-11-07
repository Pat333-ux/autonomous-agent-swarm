"""
Autonomous Agent Swarm Dispatcher
Routes specialized tasks (Security, Testing, Docs) across governed repositories
while enforcing live constitutional policy from autonomous-governance-core.
Governing Authority: Governing Officer Tarwater
"""

import os
import sys
import yaml
import base64
import logging
import argparse
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

GITHUB_API_URL = "https://api.github.com"
CORE_REPO = "Pat333-ux/autonomous-governance-core"


def get_github_headers() -> dict:
    token = os.getenv("GH_PAT") or os.getenv("GITHUB_TOKEN")
    if not token:
        raise EnvironmentError("Missing GH_PAT or GITHUB_TOKEN environment variable.")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }


def fetch_live_constitution_policy() -> dict:
    """
    Pulls the authoritative governance_config.yaml directly from autonomous-governance-core
    so no swarm agent can operate if Governing Officer Tarwater engages the kill switch.
    """
    headers = get_github_headers()
    url = f"{GITHUB_API_URL}/repos/{CORE_REPO}/contents/governance_config.yaml"
    resp = requests.get(url, headers=headers, timeout=15)

    if resp.status_code == 200:
        encoded = resp.json().get("content", "")
        raw_yaml = base64.b64decode(encoded).decode("utf-8")
        return yaml.safe_load(raw_yaml)

    logging.warning("Could not fetch remote policy from core; falling back to local governance_config.yaml")
    with open("governance_config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def verify_command_clearance(policy: dict) -> None:
    """Article III.2: Halts all swarm agents immediately if kill switch is active."""
    override_cfg = policy.get("communication_and_oversight", {}).get("emergency_override", {})
    env_kill = os.getenv("TARWATER_KILL_SWITCH", "false").lower() == "true"

    if override_cfg.get("global_kill_switch") or env_kill:
        logging.critical("EMERGENCY OVERRIDE ACTIVE: Swarm execution halted by Governing Officer Tarwater.")
        raise SystemExit(1)


def dispatch_agent(role: str, target_repo: str) -> None:
    """Validates constitutional clearance and launches the requested specialized worker."""
    policy = fetch_live_constitution_policy()
    verify_command_clearance(policy)

    logging.info(f"Clearance verified. Dispatching [{role.upper()}] agent to target: {target_repo}")

    if role == "security":
        from agents.security_auditor import run_security_audit
        run_security_audit(target_repo, policy)
    elif role == "tests":
        from agents.test_generator import run_test_generation
        run_test_generation(target_repo, policy)
    elif role == "docs":
        from agents.doc_sync_agent import run_doc_sync
        run_doc_sync(target_repo, policy)
    elif role == "all":
        from agents.security_auditor import run_security_audit
        from agents.test_generator import run_test_generation
        from agents.doc_sync_agent import run_doc_sync
        run_security_audit(target_repo, policy)
        run_test_generation(target_repo, policy)
        run_doc_sync(target_repo, policy)
    else:
        raise ValueError(f"Unknown swarm agent role: {role}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonomous Agent Swarm Dispatcher")
    parser.add_argument(
        "--role",
        choices=["security", "tests", "docs", "all"],
        default="all",
        help="Specialized agent role to execute"
    )
    parser.add_argument(
        "--target",
        default=CORE_REPO,
        help="Target GitHub repository (owner/repo) to inspect and assist"
    )
    args = parser.parse_args()
    dispatch_agent(args.role, args.target)
