# discord-linux-bridge

A small, focused Discord bot that provides an interactive, persistent Linux sandbox on the host using Docker. The bot exposes a few slash commands to execute shell commands inside a persistent container, list supported distributions, and switch the sandbox distro. It's implemented in Python (see `bot.py`) and uses the Docker SDK for Python to create and manage the sandbox containers.

Important: this project can run arbitrary shell commands in containers on the host. Review the security guidance below before deploying.

---

## Highlights / features

- Persistent sandbox container (created and managed via the Docker SDK)
- /term — execute a shell command inside the sandbox and return stdout/stderr
- /distros — list supported Linux distribution images
- /distro — switch the sandbox to a different distribution image
- Built-in container hardening options (read-only rootfs, dropped capabilities, mem and CPU limits)
- Autocomplete for distro names in the /distro command
- Lightweight: single main bot file (`bot.py`) and a Dockerfile / docker-compose for containerized deployment

---

## What the bot does (implementation notes)

- Entry point: `bot.py` — run as a script (`python bot.py`) or via the provided Dockerfile.
- Reads the Discord token from environment variable `DISCORD_TOKEN`.
- Uses the Docker SDK (`docker.from_env()`) to create/manage a persistent container.
- Supported distributions (configured in `bot.py`):
  - arch → `archlinux:latest` (default active image)
  - alpine → `alpine:latest`
  - debian → `debian:bookworm-slim`
  - ubuntu → `ubuntu:24.04`
  - fedora → `fedora:latest`
- Sandbox container settings (from code):
  - Keeps container alive with `tail -f /dev/null`
  - `mem_limit="256m"`, `cpu_quota=20000` (approx 20% of one CPU)
  - `read_only=True`, `cap_drop=["ALL"]`
  - `environment` is restricted to SAFE_ENV: PATH, LANG, TERM
  - Default container base name: `discord-linux-shell-<distro>`

---

## Requirements

- Python 3.10+ (3.11 recommended)
- Docker daemon accessible to the user running the bot (if using Docker features)
- pip packages listed in `requirements.txt` (includes discord.py and docker)
- A Discord bot token with the application registered and the bot invited to your guild

---

## Quick start — local (development)

1. Clone and change into repo:

```bash
git clone https://github.com/MrBlackReal/discord-linux-bridge.git
cd discord-linux-bridge
```

2. Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Set the Discord token and run:

```bash
export DISCORD_TOKEN="YOUR_BOT_TOKEN"
python bot.py
```

On startup the bot will try to sync slash commands and ensure a persistent sandbox container is running (default: Arch image).

---

## Quick start — containerized

The repository includes a Dockerfile and example `docker-compose.yml`. Because the bot uses the Docker SDK to create/manage containers on the host, running inside a container requires access to the host Docker socket.

Example Docker run (not recommended for untrusted networks without extra hardening):

```bash
docker build -t discord-linux-bridge:latest .

docker run -d \
  --name discord-linux-bridge \
  -e DISCORD_TOKEN="YOUR_BOT_TOKEN" \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  discord-linux-bridge:latest
```

docker-compose example (see provided `docker-compose.yml` in this repo):
- Mount `/var/run/docker.sock` into the container so the bot can create the sandbox containers on the host.
- Consider running the bot with restricted resources and user.

Security note: Mounting the Docker socket into a container gives it high privileges over the host. Use this only in trusted environments and consider alternatives (e.g., running the bot on the host directly).

---

## Bot commands (slash commands)

- /term command
  - Usage: `/term command:<shell command string>`
  - Runs the provided command inside the persistent sandbox container using `/bin/sh -c`.
  - Returns command output (stdout/stderr) as Discord messages.
  - Handles container self-repair: if the persistent container appears unhealthy, the bot will attempt to remove and recreate it and inform the user.
  - Output is truncated to fit Discord's message limits if necessary.

- /distros
  - Lists supported distro images and indicates which distro is active.

- /distro name:<distro>
  - Switch the persistent sandbox to another supported distro.
  - Stops and removes the old container and creates a new container for the requested image.

Autocomplete is provided for the `name` parameter of /distro.

---

## Security guidance (read carefully)

This bot can execute arbitrary commands inside containers that run on the Docker host. Even though the project applies container-level hardening (read-only filesystem, dropped capabilities, resource limits), there are significant risks:

- Avoid inviting this bot to untrusted servers or exposing it to untrusted users.
- Restrict who can use the bot using Discord permissions, roles, or by extending the code to check user IDs.
- Do not mount sensitive host directories into the sandbox containers.
- Consider adding additional sandboxing layers (e.g., user namespaces, seccomp profiles, gVisor) for higher assurance.
- If running the bot inside Docker, remember that exposing the Docker socket to the container is effectively root on the host — treat with extreme caution.

---

## Recommended deployment notes

- Run the bot as a dedicated low-privilege user.
- Keep the Docker daemon hardened and up to date.
- Use Discord bot permissions and server configuration to limit who can interact with the bot.
- Consider adding a command whitelist or an allowlist for commands the bot may run (not present in current code).

---

## Troubleshooting

- "FATAL: DISCORD_TOKEN environment variable not found." — set `DISCORD_TOKEN` before starting the bot.
- Container creation errors — ensure the process has permission to talk to the Docker daemon (and that the Docker daemon is running).
- Bot can't access a channel or register slash commands — ensure the bot is invited to the guild with application.commands scope and has appropriate channel permissions.

For logs, check stdout/stderr (or systemd journal if run as a service). The bot uses logging to stdout.

---

## Files of interest

- `bot.py` — main bot implementation and entrypoint
- `Dockerfile` — container image build (for the bot itself)
- `docker-compose.yml` — example compose file
- `requirements.txt` — Python dependencies

---

## Contributing

Contributions, bug reports, and improvements are welcome. Suggested improvements:
- Add user/role-based access control and command allowlists
- Add per-command execution timeouts and safer sandboxing
- Add tests for command execution and Docker interactions

---

## License

No license file is included by default in this repository. Add a LICENSE file (for example, MIT) and update this section accordingly.

---
