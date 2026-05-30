import os
import secrets
import sys
import time

from crackyard.providers.base import Provider

SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

# Even once the instance reports "running", the SSH daemon may need a few more
# seconds to come up. Wait briefly so the auto-connect doesn't hit a refused port.
SSH_GRACE_SECONDS = 7


def wait_for_sshd(seconds: int = SSH_GRACE_SECONDS) -> None:
    if not sys.stdout.isatty():
        time.sleep(seconds)
        return
    deadline = time.time() + seconds
    i = 0
    while time.time() < deadline:
        remaining = max(0, int(round(deadline - time.time())))
        sys.stdout.write(f"\r {SPINNER_FRAMES[i % len(SPINNER_FRAMES)]} Waiting for SSH daemon ({remaining}s)")
        sys.stdout.flush()
        i += 1
        time.sleep(0.1)
    sys.stdout.write("\r\033[K")
    sys.stdout.flush()


def generate_label() -> str:
    return f"cy-{secrets.token_hex(2)}"


def ssh_argv(host: str, port: int, key: str | None) -> list[str]:
    argv = ["ssh", f"root@{host}", "-p", str(port)]
    if key:
        argv += ["-i", os.path.expanduser(key)]
    return argv


def find_instance_by_label(provider: Provider, label: str) -> dict:
    instances = provider.list_instances(label_prefix="cy-")
    match = next((i for i in instances if i.get("label") == label), None)
    if match is None:
        raise SystemExit(f"No instance found with label {label!r}.")
    return match


def format_uptime(start_date: float | int | None) -> str:
    if start_date is None:
        return "-"
    seconds = max(0, int(time.time() - float(start_date)))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def estimated_cost(dph: float | None, start_date: float | int | None) -> float:
    if dph is None or start_date is None:
        return 0.0
    hours = max(0.0, (time.time() - float(start_date)) / 3600)
    return float(dph) * hours


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: list[str]) -> str:
        return "  ".join(cell.ljust(w) for cell, w in zip(cells, widths))

    lines = [fmt_row(headers), fmt_row(["-" * w for w in widths])]
    lines.extend(fmt_row(row) for row in rows)
    return "\n".join(lines)
