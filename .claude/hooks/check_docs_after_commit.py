"""PostToolUse hook: after `git commit`, remind Claude to check whether
CLAUDE.md / .claude/skills/*/SKILL.md need updating for the change just committed.

This repo's convention is that substantive code changes (new architectural
patterns, new conventions) get a follow-up doc-update commit. This hook exists
because that step was skipped for a few commits in a row (data-table.js
convention, ServerTable helper, side-pane nav) and the user wants it automated
rather than relied on from memory.

The settings.json matcher's "if" condition alone isn't reliably gating this to
git-commit-only invocations, so the script re-checks the actual command itself
(read from the PostToolUse stdin payload) and exits silently for anything else.
"""
import json
import subprocess
import sys


def ran_git_commit():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return False
    command = payload.get("tool_input", {}).get("command", "")
    import re
    return bool(re.search(r"(^|[;&|]\s*)git\s+commit\b", command))


def changed_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.splitlines() if f.strip()]


def main():
    if not ran_git_commit():
        return

    files = changed_files()
    if not files:
        return

    docs_already_touched = any(
        f == "CLAUDE.md" or f.startswith(".claude/skills/")
        for f in files
    )
    if docs_already_touched:
        return

    message = (
        "The commit just made changed: " + ", ".join(files) + ". "
        "Before moving on, check whether CLAUDE.md or .claude/skills/*/SKILL.md "
        "need updating — this repo's convention is that a new architectural "
        "pattern, convention, or behavior change gets a follow-up doc-update "
        "commit (see e.g. 349b9ae, 451a273, 9a731fd). If nothing here rises to "
        "that level, no action needed."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": message,
        }
    }))


if __name__ == "__main__":
    main()
