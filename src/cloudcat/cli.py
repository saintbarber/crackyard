import argparse
import os

from dotenv import load_dotenv

from cloudcat.config import load_config
from cloudcat.providers import PROVIDER_NAMES, get_provider
from cloudcat.utils import estimated_cost, format_table, format_uptime, generate_label

BOOT_TIMEOUT_SECONDS = 600

# GPU families - vast.ai gpu_name values grouped by hashcat-relevant generations.
# These names may need adjustment if vast.ai changes their naming.
GPU_FAMILIES: dict[str, list[str]] = {
    "rtx-50": ["RTX_5090", "RTX_5080", "RTX_5070_Ti", "RTX_5070", "RTX_5060_Ti", "RTX_5060"],
    "rtx-40": ["RTX_4090", "RTX_4080S", "RTX_4080", "RTX_4070S_Ti", "RTX_4070_Ti","RTX_4070S", "RTX_4070", "RTX_4060_Ti", "RTX_4060"],
    "rtx-30": ["RTX_3090_Ti", "RTX_3090", "RTX_3080_Ti", "RTX_3080","RTX_3070_Ti", "RTX_3070","RTX_3060_Ti", "RTX_3060"],
    "hopper": ["H100_SXM", "H100_PCIE", "H100_NVL", "H200"],
    "ampere-dc": ["A100_SXM4", "A100_PCIE", "A100"],
}


def cmd_search(args: argparse.Namespace) -> None:
    config = load_config()
    provider = get_provider(args.provider, config)

    # Default search values have been set
    #   Show only verified
    #   Show only rentable
    #   Show only offers with at least 1 direct port
    #   Show only offers with at least 20GB disk space
    #   Show only offers with reliability >= 0.9

    if args.gpu_family:
        gpu_names = GPU_FAMILIES[args.gpu_family]
    elif args.gpu:
        gpu_names = [args.gpu]
    else:
        gpu_names = None

    offers = provider.search_offers(
        gpu_names=gpu_names,
        num_gpus=args.number,
        limit=args.limit,
    )

    if not offers:
        print("No offers found. Try broadening your filters.")
        return

    rows: list[list[str]] = []
    for o in offers:
        offer_id = str(o.get("id", "-"))
        gpu = o.get("gpu_name") or "-"
        ram_mb = o.get("gpu_ram")
        ram_str = f"{int(ram_mb) // 1024}GB" if ram_mb else "-"
        n = str(o.get("num_gpus", "-"))
        dph = o.get("dph_total")
        dph_str = f"${float(dph):.3f}" if dph is not None else "-"
        debug = str(o.get("gpu_arch")) or "-"
        rows.append([offer_id, gpu, ram_str, n, dph_str, debug])

    headers = ["Offer ID", "GPU Name", "GPU RAM", "Num GPUs", "$/hr", "Debug"]
    print(format_table(headers, rows))


def cmd_list(args: argparse.Namespace) -> None:
    config = load_config()
    provider = get_provider(args.provider, config)

    label_prefix = None if args.all else "cc-"
    instances = provider.list_instances(label_prefix=label_prefix)

    if not instances:
        if args.all:
            print("No instances found.")
        else:
            print(
                "No cloudcat instances found. "
                "Use --all to show all vast.ai instances."
            )
        return

    rows: list[list[str]] = []
    for inst in instances:
        label = inst.get("label") or "-"
        instance_id = str(inst.get("id", "-"))
        gpu = inst.get("gpu_name") or "-"
        status = inst.get("actual_status") or "-"
        dph = inst.get("dph_total")
        dph_str = f"${float(dph):.3f}" if dph is not None else "-"
        start = inst.get("start_date")
        uptime = format_uptime(start)
        cost_str = f"${estimated_cost(dph, start):.2f}"
        rows.append([label, instance_id, gpu, status, dph_str, uptime, cost_str])

    headers = ["Label", "Instance ID", "GPU Name", "Status", "$/hr", "Uptime", "Est. Cost"]
    print(format_table(headers, rows))


def _ssh_argv(host: str, port: int, key: str | None) -> list[str]:
    argv = ["ssh", f"root@{host}", "-p", str(port)]
    if key:
        argv += ["-i", os.path.expanduser(key)]
    return argv


def cmd_create(args: argparse.Namespace) -> None:
    config = load_config()
    template_hash = config.require_template_hash()
    # Resolve the SSH key before spending money, so a misconfigured key
    # fails fast instead of after the instance has booted and started billing.
    ssh_key = args.key or config.require_ssh_key()
    provider = get_provider(args.provider, config)

    label = generate_label()
    print(f"Creating instance (offer={args.offer_id}, label={label})...")
    instance_id = provider.create_instance(
        offer_id=args.offer_id,
        template_id=template_hash,
        label=label,
    )
    print(f"Instance {instance_id} created. Waiting for boot...")

    ready = provider.wait_for_ready(instance_id, timeout=BOOT_TIMEOUT_SECONDS)
    if not ready:
        print(
            f"Instance {instance_id} failed to reach 'running' state. "
            "Destroying to stop billing."
        )
        provider.destroy_instance(instance_id)
        raise SystemExit(1)

    host, port = provider.get_ssh_info(instance_id)
    argv = _ssh_argv(host, port, ssh_key)
    print(f"Instance ready. Label: {label}  Instance ID: {instance_id}")
    print(f"Connecting: {' '.join(argv)}")
    os.execvp("ssh", argv)


def _find_instance_by_label(provider, label: str) -> dict:
    instances = provider.list_instances(label_prefix="cc-")
    match = next((i for i in instances if i.get("label") == label), None)
    if match is None:
        raise SystemExit(f"No instance found with label {label!r}.")
    return match


def cmd_pull(args: argparse.Namespace) -> None:
    config = load_config()
    provider = get_provider(args.provider, config)

    match = _find_instance_by_label(provider, args.label)
    instance_id = str(match.get("id"))

    print(f"Pulling {len(args.paths)} file(s) from {args.label} ({instance_id})...")
    provider.pull_files(instance_id, args.paths, local_dir="./")


def cmd_ssh(args: argparse.Namespace) -> None:
    config = load_config()
    provider = get_provider(args.provider, config)

    match = _find_instance_by_label(provider, args.label)
    instance_id = str(match.get("id"))
    status = match.get("actual_status")
    if status != "running":
        raise SystemExit(
            f"Instance {args.label} ({instance_id}) is not running "
            f"(status={status!r})."
        )

    ssh_key = args.key or config.require_ssh_key()
    host, port = provider.get_ssh_info(instance_id)
    argv = _ssh_argv(host, port, ssh_key)
    print(f"Connecting: {' '.join(argv)}")
    os.execvp("ssh", argv)


def cmd_destroy(args: argparse.Namespace) -> None:
    config = load_config()
    provider = get_provider(args.provider, config)

    match = _find_instance_by_label(provider, args.label)
    instance_id = str(match.get("id"))

    if args.pull:
        print(f"Pulling {len(args.pull)} file(s) from {args.label} ({instance_id})...")
        provider.pull_files(instance_id, args.pull, local_dir="./")

    print(f"Destroying instance {args.label} ({instance_id})...")
    provider.destroy_instance(instance_id)
    print(f"Destroyed {args.label}.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cloudcat",
        description="Provider-agnostic CLI for managing cloud GPU instances for hashcat",
    )

    # Provider selection with default from env var or "vastai"

    parser.add_argument(
        "--provider",
        choices=PROVIDER_NAMES,
        default=os.environ.get("CLOUDCAT_PROVIDER", "vastai"),
        help="Cloud provider to use (default: vastai, or $CLOUDCAT_PROVIDER)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Search command - lists available GPU offers, optionally filtered by --gpu and --number (1, 2, 4, 8, or 9+), capped by --limit

    p_search = subparsers.add_parser("search", help="Search for available GPU offers")
    gpu_group = p_search.add_mutually_exclusive_group()
    gpu_group.add_argument(
        "--gpu",
        help="Exact GPU model name (e.g. RTX_4090, A100_SXM4)",
    )
    gpu_group.add_argument(
        "--gpu-family",
        choices=list(GPU_FAMILIES),
        help="GPU family filter (e.g. rtx-50, rtx-40, hopper)",
    )
    p_search.add_argument(
        "--number",
        default="1",
        help="Min number of GPUs per instance (default: 1)",
    )
    p_search.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of results to show (default: 20)",
    )
    p_search.set_defaults(func=cmd_search)

    # List command - lists all isntances created by cloudcat (those with label starting with "cc-"), or all instances if --all is used

    p_list = subparsers.add_parser("list", help="List instances created by cloudcat")
    p_list.add_argument(
        "--all",
        action="store_true",
        help="Show all instances, not just those with the cc- prefix",
    )
    p_list.set_defaults(func=cmd_list)

    # Create command - rents an offer, waits for boot, and execs into ssh.

    p_create = subparsers.add_parser("create", help="Create an instance from an offer and SSH in")
    p_create.add_argument(
        "--offer-id",
        type=int,
        required=True,
        help="Offer ID from `cloudcat search` output",
    )
    p_create.add_argument(
        "--key",
        "-i",
        help="Path to SSH private key (passed to ssh -i). Defaults to $CLOUDCAT_SSH_KEY.",
    )
    p_create.set_defaults(func=cmd_create)

    # Destroy command - pulls files (if --pull given) then destroys the instance.

    p_destroy = subparsers.add_parser("destroy", help="Pull files from an instance and destroy it")
    p_destroy.add_argument(
        "--label",
        required=True,
        help="Label of the instance to destroy (e.g. cc-a3f7)",
    )
    p_destroy.add_argument(
        "--pull",
        action="append",
        default=[],
        metavar="REMOTE_PATH",
        help="Remote file path to download before destroy (repeatable)",
    )
    p_destroy.set_defaults(func=cmd_destroy)

    # Pull command - download files from a running instance without destroying it.

    p_pull = subparsers.add_parser("pull", help="Download files from an instance")
    p_pull.add_argument(
        "--label",
        required=True,
        help="Label of the instance to pull from (e.g. cc-a3f7)",
    )
    p_pull.add_argument(
        "paths",
        nargs="+",
        metavar="REMOTE_PATH",
        help="One or more remote file paths to download into the current directory",
    )
    p_pull.set_defaults(func=cmd_pull)

    # SSH command - reconnect to a running instance by label.

    p_ssh = subparsers.add_parser("ssh", help="SSH into a running instance by label")
    p_ssh.add_argument(
        "--label",
        required=True,
        help="Label of the instance to connect to (e.g. cc-a3f7)",
    )
    p_ssh.add_argument(
        "--key",
        "-i",
        help="Path to SSH private key (passed to ssh -i). Defaults to $CLOUDCAT_SSH_KEY.",
    )
    p_ssh.set_defaults(func=cmd_ssh)

    return parser


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
