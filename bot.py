import discord
from discord.ext import commands
from discord import app_commands

from typing import List

import docker
import asyncio
import logging

import sys
import os

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ],
    force=True,
)

# --- Constants ---
SUPPORTED_DISTROS = {
    "alpine": "alpine:latest",
    "debian": "debian:bookworm-slim",
    "ubuntu": "ubuntu:24.04",
    "fedora": "fedora:latest",
    "arch": "archlinux:latest"
}

CURRENT_DISTRO_IMAGE = SUPPORTED_DISTROS['arch']
CONTAINER_BASE_NAME = "discord-linux-shell"

SAFE_ENV = {
    'PATH': '/usr/bin:/bin',
    'LANG': 'C.UTF-8',
    'TERM': 'xterm'
}

# --- Setup discord bot ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- Container Management ---
docker_client = docker.from_env()

def get_container_id() -> str:
    return f"{CONTAINER_BASE_NAME}-{CURRENT_DISTRO_IMAGE.split(':')[0]}"

def get_sandbox():
    return {
        "container": get_container_id(),
        "distro": CURRENT_DISTRO_IMAGE
    }

def ensure_container_running():
    """Creates or retrieves the presistent linux container"""
    global CURRENT_DISTRO_IMAGE, persistent_container

    container_id = get_container_id()

    try:
        container = docker_client.containers.get(container_id)

        if container.status != "running":
            logging.info(f"Container '{container_id}' found but stopped, starting...")
            container.start()

        logging.info(f"Ataching to existing container: '{container_id}'")

        return container
    except docker.errors.NotFound:
        logging.info(f"Container '{container_id}' not found, creating...")
        pass
    except Exception as e:
        logging.error(f"Error checking for container '{container_id}': {e}")
        raise e

    try:
        container = docker_client.containers.run(
            image=CURRENT_DISTRO_IMAGE,
            name=container_id,
            detach=True,
            tty=True,
            stdin_open=True,
            command=["tail", "-f", "/dev/null"],  # Keeps container alive
            environment=SAFE_ENV,
            mem_limit="256m",
            cpu_quota=20000,  # 20% of one CPU
            network_disabled=False,
            read_only=True,  # Security hardening
            cap_drop=["ALL"],  # Security hardening
            volumes={},
            devices=None,
        )

        logging.info(f"Successfully created container: {container.name}")

        return container
    except Exception as e:
        logging.error(f"FATAL: Could not create container: {e}")
        raise e

# --- Bot events ---
@bot.event
async def on_ready():
    global persistent_container

    try:
        await bot.tree.sync()
        logging.info("✅ Synced slash commands.")
    except Exception as e:
        logging.error(f"[ON READY] ❌ Failed to sync slash commands: {e}")

    logging.info(f"✅ Logged in as {bot.user}")

    try:
        persistent_container = ensure_container_running()
        logging.info(f"🌐 Container active: {persistent_container.name}")
    except Exception as e:
        logging.critical(f"[ON READY] ❌ Failed to start or find container: {e}")

# --- Commands ---
@bot.tree.command(name="term", description="Execute a command in the sandbox")
@app_commands.describe(command="The shell command to execute")
async def term(interaction: discord.Interaction, command: str):
    """Executes a shell command in the persistent sandbox."""
    global persistent_container, CURRENT_DISTRO_IMAGE

    await interaction.response.defer()

    user_command = command.strip()
    container_name = get_container_id()

    # Auto-recovery check
    try:
        persistent_container.reload()
        test = persistent_container.exec_run(
            cmd=["/bin/sh", "-c", "command -v sh"], tty=False
        )
        if test.exit_code != 0:
            raise Exception("Shell test failed (container unhealthy)")
    except Exception as e:
        logging.warning(f"Container unhealthy ({e}). Rebuilding...")
        await interaction.followup.send(
            "🧹 The container environment was unhealthy. Rebuilding..."
        )

        try:
            old_container = docker_client.containers.get(container_name)
            old_container.remove(force=True)
            logging.info("Removed unhealthy container.")
        except docker.errors.NotFound:
            pass  # Ignore if it doesn't exist
        except Exception as remove_e:
            logging.error(f"Failed to remove unhealthy container: {remove_e}")

        try:
            persistent_container = ensure_container_running()
            await asyncio.sleep(3)
            await interaction.followup.send(
                "✅ Container restored. Try your command again."
            )
            logging.info("Container restored.")
        except Exception as rebuild_e:
            logging.error(f"Failed to rebuild container: {rebuild_e}")
            await interaction.followup.send(f"❌ Container rebuild FAILED: {rebuild_e}")
        return

    # Execute the user command
    try:
        logging.info(f"[{container_name}] Executing command: '{user_command}'")

        exec_result = persistent_container.exec_run(
            cmd=["/bin/sh", "-c", user_command], tty=True, demux=True
        )
        stdout, stderr = exec_result.output
        stdout = stdout.decode("utf-8", errors="replace").strip() if stdout else ""
        stderr = stderr.decode("utf-8", errors="replace").strip() if stderr else ""

        prompt = f"[{CURRENT_DISTRO_IMAGE.split(':')[0]}] $ {user_command}"
        response = ""

        # Check for timeout exit code
        if exec_result.exit_code == 137:  # 128 + 9 (KILL signal)
            response += "```diff\n- ⏰ Command TIMEOUT (KILLED after 120s).\n```"
        elif exec_result.exit_code != 0 and not stderr:
            stderr = f"Command failed with exit code {exec_result.exit_code}."

        if stdout:
            response += f"```bash\n{prompt}\n{stdout}\n```"
        if stderr:
            response += f"```diff\n- ERROR:\n{stderr}\n```"
        if not response:
            response = f"```bash\n{prompt}\n✨ Command executed (exit {exec_result.exit_code}) but produced no output.\n```"

        if len(response) > 2000:
            response = response[:1997] + "```"

        await interaction.followup.send(response)

    except Exception as e:
        logging.error(f"Execution failure for command '{user_command}': {e}")
        await interaction.followup.send(f"❌ Execution failure: {e}")


@bot.tree.command(name="distros", description="List all supported Linux distros")
async def list_distros(interaction: discord.Interaction):
    """Lists the available sandbox distributions."""
    lines = []
    for name, image in SUPPORTED_DISTROS.items():
        if image == CURRENT_DISTRO_IMAGE:
            lines.append(f"- {name}: {image} **(Active)**")
        else:
            lines.append(f"- {name}: {image}")

    await interaction.response.send_message(
        "🌐 Supported distros:\n" + "\n".join(lines)
    )


@bot.tree.command(name="distro", description="Switch the sandbox distro")
@app_commands.describe(name="The name of the distro to switch to (e.g., 'alpine')")
async def switch_distro(interaction: discord.Interaction, name: str):
    """Stops the current container and starts a new one with the chosen distro."""
    global persistent_container, CURRENT_DISTRO_IMAGE

    await interaction.response.defer()

    requested = name.strip().lower()

    if requested not in SUPPORTED_DISTROS:
        await interaction.followup.send(
            f"❌ `{requested}` is unsupported. Supported options: {', '.join(SUPPORTED_DISTROS.keys())}"
        )
        return

    new_image = SUPPORTED_DISTROS[requested]

    if new_image == CURRENT_DISTRO_IMAGE:
        await interaction.followup.send(f"✅ Sandbox is already running `{requested}`.")
        return

    logging.info(f"Switching distro to '{requested}' ({new_image})")
    CURRENT_DISTRO_IMAGE = new_image
    await interaction.followup.send(
        f"🌐 Switching sandbox to `{requested}` ({CURRENT_DISTRO_IMAGE})..."
    )

    # Remove old container
    if persistent_container:
        try:
            persistent_container.stop(timeout=5)
            await interaction.followup.send("ℹ️ Stopped old sandbox. Deleting...")
            persistent_container.remove(force=True)
            logging.info("Stopped and removed old container.")
        except Exception as e:
            logging.warning(f"Could not remove old container: {e}")
            await interaction.followup.send(f"⚠️ Could not remove old container: {e}")

    # Recreate sandbox with selected distro
    try:
        persistent_container = ensure_container_running()
        await asyncio.sleep(2)  # Give Docker time to settle
        await interaction.followup.send(f"✅ Sandbox switched to `{requested}`.")
        logging.info("Successfully switched sandbox.")
    except Exception as e:
        logging.error(f"Failed to switch distro: {e}")
        await interaction.followup.send(f"❌ Failed to switch distro: {e}")


# --- Autocompletion ---
@switch_distro.autocomplete("name")
async def distro_autocomplete(
    interaction: discord.Interaction, current: str
) -> List[app_commands.Choice[str]]:
    """Provides autocomplete choices for the /distro command."""
    choices = list(SUPPORTED_DISTROS.keys())
    return [
        app_commands.Choice(name=choice, value=choice)
        for choice in choices
        if current.lower() in choice.lower()
    ]


def main():
    if not (__name__ == "__main__"):
        return

    # --- Run Bot ---
    TOKEN = os.environ.get("DISCORD_TOKEN")

    if TOKEN:
        bot.run(TOKEN)
    else:
        logging.critical("FATAL: DISCORD_TOKEN environment variable not found.")

main()