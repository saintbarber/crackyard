# cloudcat

A provider-agnostic CLI for renting cloud GPU instances and dropping straight into an SSH session — built for running [hashcat](https://hashcat.net/hashcat/) on someone else's hardware.

cloudcat manages the *infrastructure* lifecycle: it searches for available GPUs, rents one, waits for it to boot, and hands your terminal over to a live SSH session so you can run hashcat interactively. When you're done, it pulls your results back and tears the instance down so the meter stops running.

It is **not** a hashcat wrapper. It doesn't parse, proxy, or stream hashcat — it just gets you a GPU and a shell.

[vast.ai](https://vast.ai) is the first (and currently only) supported provider, but the codebase is built around a provider abstraction so AWS, RunPod, and others can be added later.

## Features

- **Search** available GPU offers, filtered by exact model or by GPU family, sorted cheapest-first.
- **Create** an instance from an offer, auto-labelled, with boot polling and a live spinner — then `exec` straight into SSH.
- **List** your cloudcat instances with uptime and running cost estimates.
- **Reconnect** to a running instance by label at any time.
- **Pull** files (potfiles, cracked hashes, etc.) off an instance.
- **Destroy** an instance, optionally pulling files first, so billing stops cleanly.
- **Native SSH** via `execvp` — full TTY, so hashcat's interactive controls (`s`, `p`, `q`, …) all work.

## Requirements

- Python 3.10+
- A [vast.ai](https://vast.ai) account and API key
- A vast.ai **template hash** (defines the Docker image/config your instances boot with)
- An SSH private key registered with vast.ai

## Installation

Clone the repo and install it (a virtualenv is recommended):

```bash
git clone <your-repo-url> cloudcat
cd cloudcat

python -m venv .venv
source .venv/bin/activate        # fish: source .venv/bin/activate.fish

pip install -e .
```

This installs the `cloudcat` command. You can also run it without installing via `python -m cloudcat`.

## Configuration

cloudcat reads its settings from a `.env` file in the project root. Copy the template and fill it in:

```bash
cp .env.example .env
```

```dotenv
# Your vast.ai API key
VAST_API_KEY=your_api_key_here

# The vast.ai template hash your instances boot from
CLOUDCAT_TEMPLATE_HASH=your_template_hash_here

# Path to the SSH private key used to connect to instances
CLOUDCAT_SSH_KEY=~/.ssh/id_ed25519

# Optional: which provider to use (default: vastai)
# CLOUDCAT_PROVIDER=vastai
```

If a required value is missing, cloudcat tells you exactly what to set.

> **Note:** vast.ai requires an SSH key to connect to instances. Make sure the **public** half of `CLOUDCAT_SSH_KEY` is added to your vast.ai account. You can override the key per-command with `--key`/`-i`.

## Usage

```
cloudcat [--provider vastai] <command> [options]
```

### `search` — find available GPUs

```bash
cloudcat search --gpu RTX_4090
cloudcat search --gpu-family rtx-40 --number 2 --limit 30
```

| Flag | Description |
|------|-------------|
| `--gpu` | Exact GPU model name (e.g. `RTX_4090`, `A100_SXM4`) |
| `--gpu-family` | A family of GPUs: `rtx-50`, `rtx-40`, `rtx-30`, `hopper`, `ampere-dc` |
| `--number` | Minimum number of GPUs per instance (default: 1) |
| `--limit` | Max results to show (default: 20) |

`--gpu` and `--gpu-family` are mutually exclusive. Results are filtered to verified, rentable, reliable offers with direct ports and adequate disk, and sorted by price ascending. Note the **Offer ID** column — you'll need it to create an instance.

### `create` — rent an instance and SSH in

```bash
cloudcat create --offer-id 1234567
cloudcat create --offer-id 1234567 --key ~/.ssh/some_other_key
```

Generates a `cc-xxxx` label, rents the offer using your template hash, polls until the instance reaches `running`, then replaces the process with an SSH session. The SSH key is validated up front so a misconfigured key fails *before* anything starts billing.

| Flag | Description |
|------|-------------|
| `--offer-id` | **(required)** Offer ID from `search` |
| `--key`, `-i` | SSH private key path (defaults to `$CLOUDCAT_SSH_KEY`) |

### `list` — see your instances

```bash
cloudcat list
cloudcat list --all
```

Shows label, instance ID, GPU, status, hourly price, uptime, and estimated cost. By default only cloudcat-created instances (`cc-` prefix) are shown; `--all` includes every vast.ai instance on your account.

### `ssh` — reconnect to a running instance

```bash
cloudcat ssh --label cc-a3f7
```

| Flag | Description |
|------|-------------|
| `--label` | **(required)** Instance label, e.g. `cc-a3f7` |
| `--key`, `-i` | SSH private key path (defaults to `$CLOUDCAT_SSH_KEY`) |

### `pull` — download files without destroying

```bash
cloudcat pull --label cc-a3f7 /root/hashcat.potfile /root/cracked.txt
```

Downloads one or more remote paths into the current directory.

### `destroy` — pull files (optional) and tear down

```bash
cloudcat destroy --label cc-a3f7
cloudcat destroy --label cc-a3f7 --pull /root/hashcat.potfile --pull /root/cracked.txt
```

| Flag | Description |
|------|-------------|
| `--label` | **(required)** Instance label |
| `--pull` | Remote path to download before destroying (repeatable) |

If a file pull fails, cloudcat warns but still destroys the instance — it won't leave a GPU running and billing.

## Typical workflow

```bash
# 1. Find a cheap 4090
cloudcat search --gpu RTX_4090

# 2. Rent it and land in a shell (note the cc-xxxx label it prints)
cloudcat create --offer-id 1234567

#    ...upload your hashes/wordlists and run hashcat interactively...

# 3. Disconnected? Hop back on
cloudcat ssh --label cc-a3f7

# 4. Grab your results and shut it down
cloudcat destroy --label cc-a3f7 --pull /root/hashcat.potfile
```

## What cloudcat does *not* do

- It's not a hashcat wrapper — it doesn't parse, proxy, or stream hashcat.
- It doesn't upload files or manage wordlists/rules — do that yourself over SSH/SCP once connected.
- It doesn't use serverless; it manages on-demand GPU instances with SSH access.

## Project layout

```
src/cloudcat/
├── __main__.py          # python -m cloudcat entry point
├── cli.py               # argparse setup + subcommand handlers
├── config.py            # .env loading and validation
├── utils.py             # label generation, table/uptime/cost formatting
└── providers/
    ├── base.py          # abstract Provider interface
    └── vastai.py        # vast.ai implementation
```

Adding a new provider means implementing the `Provider` interface in `base.py` and registering it.

## License

See repository for license details.
