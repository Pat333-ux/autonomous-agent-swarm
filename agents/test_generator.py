"""
Autonomous Test Generator Agent
Scans target repositories for missing unit tests and automatically generates
compliant pytest suites using LLM intelligence.
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


def find_modules_missing_tests(owner: str, repo: str) -> list[tuple[str, str]]:
    """Identifies Python source files in the repo that do not have a matching test_*.py file."""
    headers = get_github_headers()
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/trees/main?recursive=1"
    
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code != 200:
        url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/trees/master?recursive=1"
        resp = requests.get(url, headers=headers, timeout=15)

    if resp.status_code != 200:
        logging.error(f"Failed to fetch repo tree for {owner}/{repo}: {resp.text}")
        return []

    tree = resp.json().get("tree", [])
    all_files = {item.get("path") for item in tree if item.get("type") == "blob"}

    python_sources = []
    test_files = {f for f in all_files if f.startswith("tests/") or "test_" in f}

    for f in all_files:
        if f.endswith(".py") and not f.startswith("test_") and "tests/" not in f and not any(p.startswith(".") or p in ("venv", "__pycache__") for p in f.split("/")):
            stem = os.path.splitext(f)[0]
            expected_test_1 = f"tests/test_{os.path.basename(f)}"
            expected_test_2 = f"test_{os.path.basename(f)}"
            
            if expected_test_1 not in all_files and expected_test_2 not in all_files:
                python_sources.append(f)

    # Return list of source file paths needing tests
    missing_tuples = []
    for src in python_sources:
        # Fetch file content
        content_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{src}"
        c_resp = requests.get(content_url, headers=headers, timeout=15)
        if c_resp.status_code == 200:
            file_data = c_resp.json()
            raw_content = base64.b64decode(file_data.get("content", "")).decode("utf-8", errors="ignore")
            missing_tuples.append((src, raw_content))

    return missing_tuples


def generate_unit_tests_via_llm(file_path: str, source_code: str, policy: dict) -> str:
    """Calls an LLM API to generate a comprehensive pytest suite for the given module."""
    api_key = os.getenv("LLM_API_KEY")
    api_url = os.getenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
    model = os.getenv("LLM_MODEL", "gpt-4o")

    if not api_key:
        raise EnvironmentError("Missing LLM_API_KEY for test generation agent.")

    min_cov = policy.get("architectural_safeguards", {}).get("quality_baseline", {}).get("min_test_coverage_percent", 85.0)

    system_prompt = (
        "You are an expert QA and Test Automation Agent operating under Governing Officer Tarwater. "
        f"Your mandate is to write comprehensive unit tests using pytest that achieve at least {min_cov}% test coverage "
        "for the provided Python module. Return ONLY valid Python code starting with `import pytest` and the test functions, "
        "with no markdown code fences or conversational text."
    )

    user_prompt = (
        f"Target Module: {file_path}\n\n"
        f"Source Code:\n{source_code}\n\n"
        "Generate a complete test file (test_<filename>.py) covering all functions, edge cases, and error raising paths."
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

    if content.startswith("```"):
        lines = content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    return content + "\n"


def create_test_pull_request(owner: str, repo: str, target_source: str, test_code: str, policy: dict) -> None:
    """Commits the generated test file into tests/test_*.py and opens a Pull Request."""
    headers = get_github_headers()
    base_branch = "main"

    ref_resp = requests.get(f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/ref/heads/{base_branch}", headers=headers, timeout=15)
    if ref_resp.status_code != 200:
        base_branch = "master"
        ref_resp = requests.get(f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/ref/heads/{base_branch}", headers=headers, timeout=15)
    ref_resp.raise_for_status()
    base_sha = ref_resp.json()["object"]["sha"]

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base_name = os.path.basename(target_source)
    branch_name = f"auto-test/{os.path.splitext(base_name)[0]}-{timestamp}"

    # Create branch
    branch_payload = {"ref": f"refs/heads/{branch_name}", "sha": base_sha}
    requests.post(f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/refs", headers=headers, json=branch_payload, timeout=15).raise_for_status()

    # Commit test file
    test_file_path = f"tests/test_{base_name}"
    file_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{test_file_path}"
    
    commit_payload = {
        "message": f"[TEST-GEN] Add automated pytest suite for {target_source}",
        "content": base64.b64encode(test_code.encode("utf-8")).decode("utf-8"),
        "branch": branch_name
    }
    requests.put(file_url, headers=headers, json=commit_payload, timeout=30).raise_for_status()

    # Open PR
    approver = policy.get("operational_mandate", {}).get("require_final_approval_from", "Tarwater")
    pr_payload = {
        "title": f"[TEST-GEN] Automated Unit Tests for {target_source}",
        "head": branch_name,
        "base": base_branch,
        "body": (
            f"### Autonomous Test Generator Report\n\n"
            f"- **Target Module:** `{target_source}`\n"
            f"- **Generated Test File:** `{test_file_path}`\n"
            f"- **Executive Review Required:** Governing Officer {approver}\n\n"
            f"*Generated automatically by `autonomous-agent-swarm`.*"
        )
    }
    pr_resp = requests.post(f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls", headers=headers, json=pr_payload, timeout=30)
    if pr_resp.status_code == 201:
        logging.info(f"Opened Test Generation PR: {pr_resp.json().get('html_url')}")


def run_test_generation(target_repo: str, policy: dict) -> None:
    """Orchestrates scanning for uncovered modules and generating tests."""
    logging.info(f"Starting Test Generator Agent on {target_repo}")
    owner, repo = target_repo.split("/", 1)

    uncovered = find_modules_missing_tests(owner, repo)
    if not uncovered:
        logging.info("All modules have corresponding test suites. No test generation needed.")
        return

    for src_path, src_code in uncovered:
        logging.info(f"Generating unit tests for uncovered module: {src_path}")
        test_code = generate_unit_tests_via_llm(src_path, src_code, policy)
        create_test_pull_request(owner, repo, src_path, test_code, policy)
