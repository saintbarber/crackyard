import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class Config:
    vast_api_key: str | None
    template_hash: str | None
    ssh_key_path: str | None

    def require_vast_api_key(self) -> str:
        if not self.vast_api_key:
            raise SystemExit(
                "VAST_API_KEY is not set. Add it to .env "
                "(see .env.example for the template)."
            )
        return self.vast_api_key

    def require_template_hash(self) -> str:
        if not self.template_hash:
            raise SystemExit(
                "CLOUDCAT_TEMPLATE_HASH is not set. Add it to .env "
                "(see .env.example for the template)."
            )
        return self.template_hash

    def require_ssh_key(self) -> str:
        if not self.ssh_key_path:
            raise SystemExit(
                "No SSH private key configured. Set CLOUDCAT_SSH_KEY in .env "
                "(see .env.example) or pass --key/-i."
            )
        return self.ssh_key_path


def load_config() -> Config:
    load_dotenv()
    return Config(
        vast_api_key=os.environ.get("VAST_API_KEY"),
        template_hash=os.environ.get("CLOUDCAT_TEMPLATE_HASH"),
        ssh_key_path=os.environ.get("CLOUDCAT_SSH_KEY"),
    )
