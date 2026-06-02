import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_TEMPLATE = """\
# crackyard configuration
provider = "vastai"            # default provider; override with --provider

[vastai]
ssh_key = "~/.ssh/vast.ai"  # default key for create/ssh; override with --key/-i

[vastai.search]
# vast.ai query filter fragments, ANDed together. Edit to taste.
filters = [
    "gpu_arch=nvidia",         # only NVIDIA GPUs
    "gpu_frac=1.0",            # only whole GPUs (no fractional rentals)
    "reliability>=0.9",        # only hosts with good uptime history
    "verified=true",           # only hosts verified by vast.ai staff 
    "rentable=true",           # only hosts that are currently rentable
    "direct_port_count>=1",    # only hosts with at least 1 direct port (for SSH)
    "disk_space>=20",          # only hosts with at least 20 GB of disk space (for our default template)
]
order = "dph_total"            # sort key (cheapest first)
limit = 20                     # default for --limit
number = 1                     # default for --number (min GPUs)

[vastai.create]
disk = 20                      # GB; keep >= the disk_space filter above
image = "saintbarber/vastai-hashcat:latest"
"""

CREDENTIALS_TEMPLATE = """\
# crackyard credentials (keep private; this file is created with 0600 perms)
[vastai]
api_key = ""
"""

# Values that mean "the user hasn't filled this in yet".
_PLACEHOLDERS = {"", "..."}


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "crackyard"


def config_path() -> Path:
    return config_dir() / "config.toml"


def credentials_path() -> Path:
    return config_dir() / "credentials"


def _is_set(value: object) -> bool:
    return isinstance(value, str) and value.strip() not in _PLACEHOLDERS


def _bootstrap_if_missing() -> None:
    """Create template config files on first run, then exit telling the user to edit them."""
    cfg = config_path()
    creds = credentials_path()
    if cfg.exists() and creds.exists():
        return

    print("Welcome to crackyard! It looks like this is your first time running the tool, so let's set up some configuration.")
    print("Initializing config files...")
    config_dir().mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    if not cfg.exists():
        cfg.write_text(CONFIG_TEMPLATE)
        created.append(cfg)
    if not creds.exists():
        # Create with 0600 from the start so the key is never world-readable.
        fd = os.open(creds, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(CREDENTIALS_TEMPLATE)
        created.append(creds)

    listing = "\n".join(f"  {p}" for p in created)
    raise SystemExit(
        f"Created crackyard config:\n{listing}\n\n"
        f"Set 'api_key' in {creds} and 'template_hash' in {cfg}, then re-run."
    )


def _load_toml(path: Path) -> dict:
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"Failed to parse {path}: {e}")


@dataclass
class Config:
    provider: str
    config_data: dict
    credentials_data: dict

    def _provider_config(self, provider: str) -> dict:
        section = self.config_data.get(provider)
        return section if isinstance(section, dict) else {}

    def api_key(self, provider: str) -> str:
        creds = self.credentials_data.get(provider)
        key = creds.get("api_key") if isinstance(creds, dict) else None
        if not _is_set(key):
            raise SystemExit(
                f"No API key configured for provider {provider!r}."
                f"Set api_key under [{provider}] in {credentials_path()}"
            )
        return key  # type: ignore[return-value]

    def ssh_key(self, provider: str) -> str:

        value = self._provider_config(provider).get("ssh_key")

        if not _is_set(value):
            raise SystemExit(
                f"No ssh_key configured for provider {provider!r}. "
                f"Set ssh_key under [{provider}] in {config_path()}, or pass --key/-i."
            )
        return value  # type: ignore[return-value]

    def provider_settings(self, provider: str) -> dict:
        return self._provider_config(provider)


def load_config() -> Config:
    _bootstrap_if_missing()
    config_data = _load_toml(config_path())
    credentials_data = _load_toml(credentials_path())
    provider = config_data.get("provider") or "vastai"
    return Config(
        provider=provider,
        config_data=config_data,
        credentials_data=credentials_data,
    )
