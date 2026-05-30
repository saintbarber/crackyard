import sys
import time

from vastai import VastAI

from crackyard.config import config_path
from crackyard.providers.base import Provider
from crackyard.utils import SPINNER_FRAMES

_BOOT_ERROR_STATES = {"exited", "unknown", "offline"}

_DEFAULT_FILTERS = [
    "gpu_arch=nvidia",
    "gpu_frac=1.0",
    "reliability>=0.9",
    "verified=true",
    "rentable=true",
    "direct_port_count>=1",
    "disk_space>=20",
]
_DEFAULT_ORDER = "dph_total"
_DEFAULT_DISK = 20


class VastAIProvider(Provider):
    def __init__(self, api_key: str, settings: dict | None = None):
        self.vast = VastAI(api_key=api_key)
        settings = settings or {}
        self.search_settings = settings.get("search") or {}
        self.create_settings = settings.get("create") or {}
        # self._template_hash = settings.get("template_hash")

    def search_offers(self, gpu_names: list[str] | None, num_gpus: int | None, limit: int) -> list[dict]:
        query_parts = list(self.search_settings.get("filters") or _DEFAULT_FILTERS)

        if gpu_names:
            if len(gpu_names) == 1:
                query_parts.append(f"gpu_name={gpu_names[0]}")
            else:
                query_parts.append(f"gpu_name in [{','.join(gpu_names)}]")
        if num_gpus:
            query_parts.append(f"num_gpus>={num_gpus}")
        query = " ".join(query_parts)
        order = self.search_settings.get("order") or _DEFAULT_ORDER

        offers = self.vast.search_offers(type="on-demand", query=query, order=order, limit=limit, no_default=True) or []
        return offers

    def create_instance(self, id: int, label: str) -> str:
        if not isinstance(self.create_settings.get("image"), str) or not self.create_settings.get("image").strip():
            raise SystemExit(
                "No image configured for provider 'vastai'. "
                f"Set image under [vastai.create] in {config_path()}."
            )

        
        print(f"Creating instance (id={id}, label={label})...")
        result = self.vast.create_instance(
            id=id,
            label=label,
            image=self.create_settings.get("image"),
            runtype="ssh_direc ssh_proxy",
            disk=self.create_settings.get("disk", _DEFAULT_DISK),  # GB
        )
        if not result or not result.get("success"):
            raise SystemExit(f"create_instance failed: {result!r}")
        instance_id = result.get("new_contract")
        if not instance_id:
            raise SystemExit(f"create_instance returned no instance id: {result!r}")
        return str(instance_id)

    def wait_for_ready(self, instance_id: str) -> bool:
        deadline = time.time() + self.create_settings.get("timeout", 600)
        start = time.time()
        next_poll = 0.0
        status = "?"
        frame = 0
        tty = sys.stdout.isatty()

        try:
            while time.time() < deadline:
                if time.time() >= next_poll:
                    info = self.vast.show_instance(id=int(instance_id)) or {}
                    status = info.get("actual_status") or "?"
                    if status == "running":
                        return True
                    if status in _BOOT_ERROR_STATES:
                        return False
                    next_poll = time.time() + 10

                if tty:
                    elapsed = int(time.time() - start)
                    sys.stdout.write(
                        f"\r {SPINNER_FRAMES[frame % len(SPINNER_FRAMES)]} "
                        f"Waiting for instance (status={status}, {elapsed}s)"
                    )
                    sys.stdout.flush()
                    frame += 1
                time.sleep(0.1)
        finally:
            if tty:
                sys.stdout.write("\r\033[K")
                sys.stdout.flush()
        return False

    def list_instances(self, label_prefix: str | None = None) -> list[dict]:
        instances = self.vast.show_instances() or []
        if label_prefix is not None:
            instances = [
                i for i in instances
                if (i.get("label") or "").startswith(label_prefix)
            ]
        return instances

    def get_ssh_info(self, instance_id: str) -> tuple[str, int]:
        info = self.vast.show_instance(id=int(instance_id)) or {}
        host = info.get("public_ipaddr")
        port = info.get("ports").get("22/tcp")[0].get('HostPort')
        if not host or not port:
            raise SystemExit(
                f"Instance {instance_id} has no SSH info yet "
                f"(host={host!r}, port={port!r})"
            )
        return str(host), int(port)

    def pull_files(self, instance_id: str, remote_paths: list[str], local_dir: str) -> None:

        for path in remote_paths:
            src = f"{instance_id}:{path}"
            dst = f"local:{local_dir}"
            try:
                self.vast.copy(src=src, dst=dst)
                print(f"  pulled {path}")
            except Exception as e:
                print(f"  WARN: failed to pull {path}: {e}")

    def destroy_instance(self, instance_id: str) -> None:
        self.vast.destroy_instance(id=int(instance_id))
