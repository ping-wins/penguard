"""CLI subprocess provider — bridges to `claude` / `codex` on the host.

The cockpit invokes the locally-installed AI CLI with the user's prompt
and parses stdout. The CLI handles auth on its own (via the user's
existing login on the workstation), so the backend never sees a token.

CLI mode ONLY works when the cockpit runs natively on the workstation
where the CLI is authenticated. A Docker container won't see
`~/.claude/` or `~/.codex/`. The factory in `app/ai/preferences.py`
returns this provider when `mode == 'cli'`; the call sites surface a
clear error if the binary is missing.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from app.ai.provider import (
    AIConfigurationError,
    ChatMessage,
    ContainmentSuggestion,
    IncidentAnalysis,
    IncidentContext,
    _build_analyze_prompt,
    _build_containment_prompt,
    _chat_system_prompt,
    _parse_analysis,
    _parse_containment,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 90
MAX_OUTPUT_BYTES = 1_000_000  # 1 MB — long enough for analysis JSON, short
# enough to keep a runaway CLI from filling memory.

# Characters we refuse to accept in the binary path. We launch with
# shell=False anyway (so they aren't interpreted), but a path containing
# them is almost certainly an injection attempt rather than a real install.
_PATH_REJECTED_CHARS = ("\x00", "\n", "\r")


class CliInvocationError(RuntimeError):
    """Raised when the CLI subprocess fails (non-zero exit, timeout, etc)."""


def _validate_binary(path: str) -> Path:
    cleaned = (path or "").strip().strip('"').strip("'")
    if not cleaned:
        raise AIConfigurationError("CLI binary path is empty")
    if any(ch in cleaned for ch in _PATH_REJECTED_CHARS):
        raise AIConfigurationError("CLI binary path contains illegal characters")
    binary = Path(cleaned)
    if not binary.is_file():
        raise AIConfigurationError(
            f"CLI binary not found: {cleaned}. Pointing the cockpit at a "
            "containerised path? CLI mode requires running the backend "
            "natively on the same machine where `claude`/`codex` is "
            "installed."
        )
    return binary


def _detect_flavor(binary: Path) -> str:
    name = binary.stem.lower()
    if "claude" in name:
        return "claude"
    if "codex" in name:
        return "codex"
    return "unknown"


class CliAIProvider:
    name = "cli"

    def __init__(
        self,
        *,
        binary_path: str,
        model: str = "",
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        env_overlay: dict[str, str] | None = None,
        runner: Any | None = None,
    ) -> None:
        self.binary = _validate_binary(binary_path)
        self.flavor = _detect_flavor(self.binary)
        self.model = model
        self.timeout_seconds = max(5, int(timeout_seconds))
        self._env_overlay = dict(env_overlay or {})
        # Injectable so tests don't actually spawn a process.
        self._runner = runner or subprocess.run

    # ------------------------------------------------------------------
    # AIProvider Protocol
    # ------------------------------------------------------------------

    def chat(self, messages: list[ChatMessage], *, locale: str = "pt-BR") -> str:
        prompt = _flatten_messages(messages, system=_chat_system_prompt(locale))
        return self._run(prompt, output_format="text")

    def analyze_incident(
        self,
        context: IncidentContext,
        *,
        locale: str = "pt-BR",
    ) -> IncidentAnalysis:
        prompt = _build_analyze_prompt(context, locale=locale)
        raw = self._run(prompt, output_format="json")
        return _parse_analysis(raw, context=context, locale=locale)

    def suggest_containment(
        self,
        context: IncidentContext,
        *,
        locale: str = "pt-BR",
    ) -> ContainmentSuggestion:
        prompt = _build_containment_prompt(context, locale=locale)
        raw = self._run(prompt, output_format="json")
        return _parse_containment(raw, context=context, locale=locale)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_argv(self, *, output_format: str) -> list[str]:
        if self.flavor == "claude":
            argv = [
                str(self.binary),
                "-p",
                "--bare",
                "--no-session-persistence",
                "--permission-mode",
                "default",
            ]
            if output_format == "json":
                argv += ["--output-format", "json"]
            if self.model:
                argv += ["--model", self.model]
            return argv
        if self.flavor == "codex":
            # Codex CLI shape (best-effort; refine when we test against it):
            #   codex exec --json --model <model> "<prompt>"
            argv = [str(self.binary), "exec"]
            if output_format == "json":
                argv.append("--json")
            if self.model:
                argv += ["--model", self.model]
            return argv
        raise AIConfigurationError(
            f"Unsupported CLI flavor for binary {self.binary.name}. "
            "Use 'claude' or 'codex'."
        )

    def _run(self, prompt: str, *, output_format: str) -> str:
        argv = self._build_argv(output_format=output_format)
        env = os.environ.copy()
        env.update(self._env_overlay)
        try:
            completed = self._runner(
                argv,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                env=env,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CliInvocationError(
                f"CLI {self.binary.name} timed out after {self.timeout_seconds}s"
            ) from exc
        except FileNotFoundError as exc:
            raise AIConfigurationError(
                f"CLI binary disappeared: {self.binary}"
            ) from exc

        stdout = (completed.stdout or "")[:MAX_OUTPUT_BYTES]
        stderr = (completed.stderr or "")[:4096]

        if completed.returncode != 0:
            logger.warning(
                "cli_provider_nonzero_exit binary=%s code=%s stderr=%s",
                self.binary.name,
                completed.returncode,
                stderr[:300],
            )
            raise CliInvocationError(
                f"CLI {self.binary.name} exited {completed.returncode}: "
                f"{stderr[:200] or 'no stderr'}"
            )

        if self.flavor == "claude" and output_format == "json":
            return _extract_claude_json_result(stdout)
        return stdout.strip()


def _flatten_messages(messages: list[ChatMessage], *, system: str) -> str:
    """Collapse a chat history into a single prompt for `claude -p`.

    Claude Code's -p flag takes a single prompt; we prepend the system
    instructions and label each turn so the model has the same context
    it would have via the API.
    """
    lines: list[str] = []
    if system:
        lines.append(f"[system]\n{system}\n")
    for message in messages:
        role = (message.get("role") or "user").lower()
        content = (message.get("content") or "").strip()
        if not content:
            continue
        label = {"user": "User", "assistant": "Assistant", "system": "System"}.get(
            role, role.title()
        )
        lines.append(f"[{label}]\n{content}\n")
    lines.append("[Assistant]\n")
    return "\n".join(lines)


def _extract_claude_json_result(stdout: str) -> str:
    """Claude `--output-format json` wraps the reply in an envelope.

    The envelope shape (as of CLI 2.x):
        {"type":"result","subtype":"...","result":"<text reply>", ...}
    We unwrap to the inner reply so the existing parsers see plain text
    (which they then re-parse as JSON if the prompt asked for structured
    output).
    """
    stripped = stdout.strip()
    if not stripped:
        return ""
    try:
        envelope = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    if isinstance(envelope, dict):
        inner = envelope.get("result")
        if isinstance(inner, str):
            return inner
        if inner is not None:
            return json.dumps(inner, ensure_ascii=False)
    return stripped


def describe_cli_invocation(binary_path: str, *, model: str = "") -> dict[str, Any]:
    """Diagnostic helper — does NOT spawn the CLI, just validates.

    Used by the /api/ai/preferences/cli/probe endpoint so the Settings
    UI can show "binário encontrado" without burning a CLI call.
    """
    try:
        binary = _validate_binary(binary_path)
    except AIConfigurationError as exc:
        return {"ok": False, "error": str(exc)}
    flavor = _detect_flavor(binary)
    argv: list[str]
    if flavor == "claude":
        argv = [str(binary), "-p", "--bare", "--no-session-persistence", "--output-format", "json"]
        if model:
            argv += ["--model", model]
    elif flavor == "codex":
        argv = [str(binary), "exec", "--json"]
        if model:
            argv += ["--model", model]
    else:
        return {
            "ok": False,
            "error": f"binary {binary.name} is not a recognised AI CLI (claude/codex)",
        }
    return {
        "ok": True,
        "binary": str(binary),
        "flavor": flavor,
        "argvPreview": shlex.join(argv),
    }
