"""Interactive text chat TUI using prompt_toolkit and rich."""

from __future__ import annotations

import asyncio
import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.live import Live
from rich.text import Text

from .client import DoloresClient

console = Console()


async def chat_loop(
    server_url: str | None = None,
    api_key: str | None = None,
    provider: str | None = None,
) -> None:
    """Run the interactive chat loop."""
    client = DoloresClient(server_url=server_url, api_key=api_key, provider=provider)
    session: PromptSession = PromptSession()

    console.print("[bold]Dolores CLI[/bold] - Type your message, or 'quit' to exit.\n")

    try:
        await client.connect()
        console.print(f"[dim]Connected. Conversation: {client.conversation_id}[/dim]\n")

        while True:
            with patch_stdout():
                try:
                    user_input = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: session.prompt("You: ")
                    )
                except (EOFError, KeyboardInterrupt):
                    break

            if not user_input.strip():
                continue
            if user_input.strip().lower() in ("quit", "exit", "/quit", "/exit"):
                break

            # Stream response
            response_text = Text()
            console.print("[bold blue]Dolores:[/bold blue] ", end="")

            async for event in client.send_text(user_input):
                if event.get("type") == "response.text":
                    content = event.get("content", "")
                    console.print(content, end="")
                elif event.get("type") == "response.end":
                    console.print()  # newline
                elif event.get("type") == "error":
                    console.print(f"\n[red]Error: {event.get('message', 'Unknown error')}[/red]")

            console.print()  # blank line between exchanges

    except ConnectionRefusedError:
        console.print("[red]Could not connect to Dolores server. Is it running?[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
    finally:
        await client.close()
        console.print("[dim]Goodbye![/dim]")
