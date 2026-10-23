#!/usr/bin/env python3
"""Patch Hermes so /help and the Telegram "/" menu list the commands a person uses, from `gateway ayuda`.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: help_menu.py <path to gateway/slash_commands.py> <path to hermes_cli/commands_platforms.py>

Why (2026-10-22): Hermes's /help printed its ~80 built-ins (kanban, codex-runtime, moa... most of them for developers)
and none of the quick commands, so a person never saw /estado, /idioma or /voz; the Telegram menu had the same 60
built-ins. Now a bare /help prints `gateway ayuda` (the bridgeai commands in the person's language, Zabbix ones only on a
stack that has them) and the menu is `gateway ayuda --menu`. `/help <filter>`, `/help skills` and /commands keep
Hermes's full catalog, and every built-in still runs when typed. If `gateway` is missing or fails, both fall back to
Hermes's own list.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the
build loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: help_menu"

HELPER = '''def _aibridge_gateway(*args):
    """stdout of `gateway <args>` (bridgeai's /help and Telegram menu), "" when it is missing or fails."""
    import subprocess
    try:
        from tools.environments.local import build_subprocess_env
        env = build_subprocess_env()
    except Exception:
        env = None
    try:
        r = subprocess.run(["gateway", *args], capture_output=True, text=True, timeout=10, env=env)
    except Exception:
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


'''


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


def patch_help(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do:", path)
        return
    src = replace_once(src, "def _preview(text: str, limit: int = 60) -> str:\n",
                       MARK + "\n" + HELPER + "def _preview(text: str, limit: int = 60) -> str:\n", "helper before _preview")
    src = replace_once(
        src,
        '        """Handle /help command - list available commands."""\n'
        "        return self._telegramized_command_reply(\n"
        '            event, _execute("help", options=self._catalog_options(event)).text)\n',
        '        """Handle /help command - list available commands."""\n'
        "        " + MARK + "\n"
        "        if not event.get_command_args().strip() and not self._catalog_options(event):\n"
        '            ours = await asyncio.to_thread(_aibridge_gateway, "ayuda")\n'
        "            if ours:\n"
        "                return self._telegramized_command_reply(event, ours)\n"
        "        return self._telegramized_command_reply(\n"
        '            event, _execute("help", options=self._catalog_options(event)).text)\n',
        "/help handler",
    )
    open(path, "w", encoding="utf-8").write(src)
    print("patched:", path)


def patch_menu(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do:", path)
        return
    src = replace_once(src, "def telegram_menu_commands(max_commands: int = 100)",
                       MARK + "\n" + HELPER + "def telegram_menu_commands(max_commands: int = 100)", "helper before the menu")
    src = replace_once(
        src,
        "    core_commands = list(telegram_bot_commands(include_plugins=False))\n"
        "    entries, hidden_count = _collect_gateway_skill_entries(\n"
        '        platform="telegram",',
        "    " + MARK + "\n"
        '    ours = [ln.split("\\t", 1) for ln in _aibridge_gateway("ayuda", "--menu").splitlines() if "\\t" in ln]\n'
        "    if ours:\n"
        "        return [(name, _normalize_telegram_desc(desc)) for name, desc in ours][:max_commands], 0\n"
        "    core_commands = list(telegram_bot_commands(include_plugins=False))\n"
        "    entries, hidden_count = _collect_gateway_skill_entries(\n"
        '        platform="telegram",',
        "Telegram menu",
    )
    open(path, "w", encoding="utf-8").write(src)
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    patch_help(sys.argv[1])
    patch_menu(sys.argv[2])
