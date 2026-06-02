from abc import ABC, abstractmethod


class Provider(ABC):
    @abstractmethod
    def search_offers(
        self,
        gpu_names: list[str] | None,
        num_gpus: int | None,
        limit: int,
        **kwargs,
    ) -> list[dict]: ...

    @abstractmethod
    def create_instance(
        self,
        id: int,
        label: str,
    ) -> str: ...

    @abstractmethod
    def wait_for_ready(self, instance_id: str, timeout: int) -> bool: ...

    @abstractmethod
    def list_instances(self, label_prefix: str | None = None) -> list[dict]: ...

    @abstractmethod
    def get_ssh_info(self, instance_id: str) -> tuple[str, int]: ...

    @abstractmethod
    def pull_files(
        self,
        instance_id: str,
        remote_paths: list[str],
        local_dir: str,
    ) -> None: ...

    @abstractmethod
    def destroy_instance(self, instance_id: str) -> None: ...
