
# crackyard

A python CLI for renting cloud GPU instances and dropping straight into an SSH session - built for running [hashcat](https://hashcat.net/hashcat/).

crackyard manages the *infrastructure* lifecycle: it searches for available GPUs, rents one, waits for it to boot, and hands your terminal over to a live SSH session so you can run hashcat interactively. When you're done, it pulls your results back and tears the instance down so the meter stops running.



## Supported Providers

- [vast.ai](https://vast.ai) 

vast.ai is the first (and currently only) supported provider. Furture plans are to also include rundpod.io

## Features

- **Search** available GPU offers, filtered by exact model or by GPU family, sorted cheapest-first.
- **Create** an instance from an offer, then `exec` straight into SSH.
- **List** your crackyard instances with uptime and running cost estimates.
- **Pull** files (potfiles, cracked hashes, etc.) off an instance.
- **Destroy** an instance, optionally pulling files first, so billing stops cleanly.
- **SSH** full TTY, so hashcat's interactive controls (`s`, `p`, `q`, …) all work.
- **Tab Completion** - Simply run the completions argument to generate script

## Requirements

- Python 3.11+
- A [vast.ai](https://vast.ai) account and API key
- An SSH private key registered with vast.ai

## Installation

The recommended way to install is with [pipx](https://pipx.pypa.io), which puts `crackyard` on your PATH in its own isolated environment:

```bash
pipx install git+https://github.com/saintbarber/crackyard.git
```

Or clone and install for development (a virtualenv is recommended):

```bash
git clone https://github.com/saintbarber/crackyard.git
cd crackyard

python -m venv .venv
source .venv/bin/activate

pip install -e .
```

This installs the `crackyard` command. You can also run it without installing via `python -m crackyard`.

# Configuration

## Config files

crackyard stores its configuration under `$XDG_CONFIG_HOME/crackyard/` (i.e. `~/.config/crackyard/` by default), split into two files:

- **`config.toml`** — settings and default values which you may want to tweak.
- **`credentials`** — your API keys. Keep it private.

The first time you run any command, crackyard creates both files from templates and asks you to fill them in. Set your API key in `credentials` and your template hash in `config.toml`, then re-run.

**`credentials`:**
```toml
[vastai]
api_key = "your_api_key_here"
```

**`config.toml`:**
```toml
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
image = "saintbarber/vastai-hashcat:latest" # image used to setup hashcat in docker container, visit https://github.com/saintbarber/vastai-hashcat for more details
```

If a required value is missing, crackyard tells you exactly which file and key to set.

> **Note:** vast.ai requires an SSH key to connect to instances. Make sure the **public** half of your `ssh_key` is added to your vast.ai account. You can override the key per-command with `--key`/`-i`.

## SSH Keys

First we need to create own own SSH key pair:
```bash
ssh-keygen -t ed25519 -f ~/.ssh/vast.ai
```

## Vast.ai

### API Key

Visit vast.ai [Keys](https://cloud.vast.ai/manage-keys/) section and navigate to the API Keys tab.

Create and copy the API key into the `~/.config/crackyard/credentials` file


### Connecting SSH key

Visit vast.ai [Keys](https://cloud.vast.ai/manage-keys/) section and click +New and paste your public key. 

The path of the generated SSH private key goes in `config.toml` as `ssh_key` (see below).


## Runpod.io

#TODO

# Usage

```
crackyard [--provider vastai] <command> [options]
```

### `search` — find available GPUs

```bash
crackyard search --gpu RTX_4090
crackyard search --gpu-family rtx-40 --number 2 --limit 30
```

| Flag | Description |
|------|-------------|
| `--gpu` | Exact GPU model name (e.g. `RTX_4090`, `A100_SXM4`) |
| `--gpu-family` | A family of GPUs: `rtx-50`, `rtx-40`, `rtx-30`, `hopper`, `ampere-dc` |
| `--number` | Minimum number of GPUs per instance (default: `number` in `config.toml`, else 1) |
| `--limit` | Max results to show (default: `limit` in `config.toml`, else 20) |
| `--secure-cloud` | Only show offers which use secure datacenters |


`--gpu` and `--gpu-family` are mutually exclusive. Results are filtered to verified, rentable, reliable offers with direct ports and adequate disk, and sorted by price ascending. Note the **Offer ID** column, you'll need it to create an instance.

### `create` — rent an instance and SSH in

```bash
crackyard create --offer-id 1234567
crackyard create --offer-id 1234567 --key ~/.ssh/some_other_key
```

Generates a `cy-xxxx` label, rents the offer using your template hash, polls until the instance reaches `running`, then replaces the process with an SSH session. The SSH key is validated up front so a misconfigured key fails *before* anything starts billing.

| Flag | Description |
|------|-------------|
| `--offer-id` | **(required)** Offer ID from `search` |
| `--key`, `-i` | SSH private key path (defaults to `ssh_key` in `config.toml`) |

### `list` — see your instances

```bash
crackyard list
crackyard list --all
```

Shows label, instance ID, GPU, status, hourly price, uptime, and estimated cost. By default only crackyard-created instances (`cy-` prefix) are shown; `--all` includes every vast.ai instance on your account.

### `ssh` — reconnect to a running instance

```bash
crackyard ssh --label cy-a3f7
```

| Flag | Description |
|------|-------------|
| `--label` | **(required)** Instance label, e.g. `cy-a3f7` |
| `--key`, `-i` | SSH private key path (defaults to `ssh_key` in `config.toml`) |

### `pull` — download files from instance

```bash
crackyard pull --label cy-a3f7 /root/hashcat.potfile /root/cracked.txt
```

Downloads one or more remote paths into the current directory.

### `destroy` — pull files (optional) and tear down

```bash
crackyard destroy --label cy-a3f7
crackyard destroy --label cy-a3f7 --pull /root/hashcat.potfile /root/cracked.txt
```

| Flag | Description |
|------|-------------|
| `--label` | **(required)** Instance label |
| `--pull` | One or more remote paths to download before destroying |

If a file pull fails, crackyard warns but still destroys the instance — it won't leave a GPU running and billing.

### `completion` — enable tab completion for your shell

```bash
crackyard completion bash    # prints a bash activation script
crackyard completion zsh     # prints a zsh activation script
crackyard completion fish    # prints a fish completion script
```

The command prints the script to stdout, you decide how to install it.

**bash** — append to `~/.bashrc`:
```bash
eval "$(crackyard completion bash)"
```

**zsh** — append to `~/.zshrc`:
```bash
eval "$(crackyard completion zsh)"
```

**fish** — write it once into the completions directory (no sourcing on every shell):
```fish
crackyard completion fish > ~/.config/fish/completions/crackyard.fish
```

Tab completion works on every argument and flag, you can also tab completed your instances label.

> Tab completion calls the provider API on each tab press, so expect a brief pause the first time. If your credentials aren't configured, completion silently returns nothing rather than spewing errors over your prompt.

## Typical workflow

```bash
# 1. Find a cheap 4090
crackyard search --gpu RTX_4090

# 2. Rent it and land in a shell (note the cy-xxxx label it prints)
crackyard create --offer-id 1234567

#    ...upload your hashes/wordlists and run hashcat interactively...

# 3. Disconnected? Hop back on
crackyard ssh --label cy-a3f7

# 4. Grab your results and shut it down
crackyard destroy --label cy-a3f7 --pull /root/hashcat.potfile
```

