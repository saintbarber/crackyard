import itertools
import sys
import time

from vastai import VastAI

from cloudcat.providers.base import Provider

_BOOT_ERROR_STATES = {"exited", "unknown", "offline"}


class VastAIProvider(Provider):
    def __init__(self, api_key: str):
        self.vast = VastAI(api_key=api_key)

    def search_offers(self, gpu_names: list[str] | None, num_gpus: int | None, limit: int) -> list[dict]:
        query_parts = ["gpu_arch=nvidia", "gpu_frac=1.0","reliability>=0.9","verified=true","rentable=true", "direct_port_count>=1", "disk_space>=20"]
        # query_parts = []
        
        if gpu_names:
            if len(gpu_names) == 1:
                query_parts.append(f"gpu_name={gpu_names[0]}")
            else:
                query_parts.append(f"gpu_name in [{','.join(gpu_names)}]")
        if num_gpus:
            query_parts.append(f"num_gpus>={num_gpus}")
        query = " ".join(query_parts)
        order = "dph_total"
        
        offers = self.vast.search_offers(type="on-demand", query=query, order=order, limit=limit, no_default=True) or []
        # print(offers)
        return offers

    def create_instance(self, offer_id: int, template_id: str, label: str) -> str:
        
        result = self.vast.create_instance(
            id=offer_id,
            template_hash=template_id,
            label=label,
            disk=20, # GB
        )
        if not result or not result.get("success"):
            raise SystemExit(f"create_instance failed: {result!r}")
        instance_id = result.get("new_contract")
        if not instance_id:
            raise SystemExit(f"create_instance returned no instance id: {result!r}")
        return str(instance_id)

    def wait_for_ready(self, instance_id: str, timeout: int) -> bool:
        spinner = itertools.cycle("|/-\\")
        deadline = time.time() + timeout
        status = "?"
        start = time.time()
        tty = sys.stdout.isatty()
        last_poll = 0.0
        try:
            while time.time() < deadline:
                if time.time() - last_poll >= 10 or last_poll == 0.0:
                    info = self.vast.show_instance(id=int(instance_id)) or {}
                    status = info.get("actual_status") or "?"
                    last_poll = time.time()
                    if status == "running":
                        if tty:
                            sys.stdout.write("\r\033[K")
                            sys.stdout.flush()
                        return True
                    if status in _BOOT_ERROR_STATES:
                        if tty:
                            sys.stdout.write("\r\033[K")
                            sys.stdout.flush()
                        return False
                elapsed = int(time.time() - start)
                if tty:
                    sys.stdout.write(
                        f"\r {next(spinner)} waiting for instance "
                        f"(status={status}, {elapsed}s)"
                    )
                    sys.stdout.flush()
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
        # host = info.get("ssh_host")
        host = info.get("public_ipaddr")
        # port = info.get("ssh_port")
        port = info.get("ports").get("22/tcp")[0].get('HostPort') # Hacky TODO: Fix
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
