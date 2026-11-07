"""
Autonomous Documentation Synchronization Agent
Scans target repositories for architectural changes and automatically updates
README.md and documentation files to reflect current reality.
Governing Authority: Governing Officer Tarwater
"""

import os
import base64
import logging
import requests
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

GITHUB_API_URL = "https://api.github.com"


def get_github_headers() -> dict:
    token = os.getenv("GH_PAT") or os.getenv("GITHUB_TOKEN")
    if not token:
        raise EnvironmentError("Missing GH_PAT or GITHUB_TOKEN environment variable.")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }


def fetch_repo_file_tree(owner: str, repo: str) -> list[str]:
    """Fetches all repository file paths."""
    headers = get_github_headers()
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/trees/main?recursive=1"
    
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code != 200:
        url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/trees/master?recursive=1"
        resp = requests.get(url, headers=headers, timeout=15)

    if resp.status_code != 200:
        return []

    tree = resp.json().get("tree", [])
    return [item.get("path") for item in tree if item.get("type") == "blob"]


def generate_updated_readme_via_llm(repo_name: str, file_paths: list[str], policy: dict) -> str:
    """Uses LLM intelligence to synthesize a clean, updated README.md reflecting current files."""
    api_key = os.getenv("LLM_API_KEY")
    api_url = os.getenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
    model = os.getenv("LLM_MODEL", "gpt-4o")

    if not api_key:
        raise EnvironmentError("Missing LLM_API_KEY for documentation sync agent.")

    system_prompt = (
        "You are an expert Technical Documentation Agent operating under Governing Officer Tarwater. "
        "Your mandate is to generate a comprehensive, professional, and well-structured README.md in Markdown format "
        "based on the repository's current file tree. Return ONLY valid Markdown content with no conversational wrapper."
    )

    file_list_str = "\n".join(f"- `{fp}`" for fp in sorted(file_paths))
    user_prompt = (
        f"Repository Name: {repo_name}\n\n"
        f"Current File Tree:\n{file_list_str}\n\n"
        "Generate a complete README.md that details the architecture, file descriptions, and operational instructions "
        "under Governing Officer Tarwater's executive governance framework."
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2
    }

    resp = requests.post(api_url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()

    if content.startswith("```markdown"):
        lines = content.splitlines()[1:-1]
        content = "\n".join(lines).strip()
    elif content.startswith("```"):
        lines = content.splitlines()[1:-1]
        content = "\n".join(lines).strip()

    return content + "\n"


def commit_readme_update(owner: str, repo: str, new_readme_content: str, policy: dict) -> None:
    """Commits the updated README.md to a new branch and opens a Pull Request."""
    headers = get_github_headers()
    base_branch = "main"

    ref_resp = requests.get(f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/ref/heads/{base_branch}", headers=headers, timeout=15)
    if ref_resp.status_code != 200:
        base_branch = "master"
        ref_resp = requests.get(f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/ref/heads/{base_branch}", headers=headers, timeout=15)
    ref_resp.raise_for_status()
    base_sha = ref_resp.json()["object"]["sha"]

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    branch_name = f"auto-docs/readme-sync-{timestamp}"

    # Create branch
    branch_payload = {"ref": f"refs/heads/{branch_name}", "sha": base_sha}
    requests.post(f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/refs", headers=headers, json=branch_payload, timeout=15).raise_for_status()

    # Get existing README sha if present
    readme_path = "README.md"
    existing = requests.get(f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{readme_path}", headers=headers, params={"ref": branch_name}, timeout=15)
    file_sha = existing.json().get("sha") if existing.status_code == 200 else None

    commit_payload = {
        "message": "[DOCS-SYNC] Automatically synchronize README.md with repository architecture",
        "content": base64.b64encode(new_readme_content.encode("utf-8")).decode("utf-8"),
        "branch": branch_name
    }
    if file_sha:
        commit_payload["sha"] = file_sha

    requests.put(f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{readme_path}", headers=headers, json=commit_payload, timeout=30).raise_for_status()

    approver = policy.get("operational_mandate", {}).get("require_final_approval_from", "Tarwater")
    pr_payload = {
        "title": "[DOCS-SYNC] Synchronize Documentation with Repository State",
        "head": branch_name,
        "base": base_branch,
        "body": (
            f"### Documentation Synchronization Report\n\n"
            f"- **Target Repository:** `{owner}/{repo}`\n"
            f"- **Updated File:** `README.md`\n"
            f"- **Executive Review Required:** Governing Officer {approver}\n\n"
            f"*Generated automatically by `autonomous-agent-swarm`.*"
        )
    }
    pr_resp = requests.post(f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls", headers=headers, json=pr_payload, timeout=30)
    if pr_resp.status_code == 201:
        logging.info(f"Opened Documentation Sync PR: {pr_resp.json().get('html_url')}")


def run_doc_sync(target_repo: str, policy: dict) -> None:
    """Orchestrates document synchronization for the target repository."""
    logging.info(f"Starting Documentation Sync Agent on {target_repo}")
    owner, repo = target_repo.split("/", 1)

    file_paths = fetch_repo_file_tree(owner, repo)
    if not file_paths:
        logging.warning("No files found or unable to fetch tree.")
        return

    new_readme = generate_updated_readme_via_llm(repo, file_paths, policy)
    commit_readme_update(owner, repo, new_readme, policy)
