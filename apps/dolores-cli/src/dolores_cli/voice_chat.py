"""Interactive voice chat using push-to-talk."""

from __future__ import annotations

import asyncio

from rich.console import Console

from .audio import AudioPlayer, AudioRecorder, pcm_to_webm
from .client import DoloresClient

console = Console()


async def voice_chat_loop(
    server_url: str | None = None,
    api_key: str | None = None,
    provider: str | None = None,
    voice_id: str | None = None,
) -> None:
    """Run the interactive voice chat loop with push-to-talk."""
    from .config import settings

    client = DoloresClient(server_url=server_url, api_key=api_key, provider=provider)
    recorder = AudioRecorder()
    player = AudioPlayer()
    voice = voice_id or settings.voice_id

    console.print("[bold]Dolores Voice Chat[/bold]")
    console.print("Press [bold]Enter[/bold] to start recording, [bold]Enter[/bold] again to stop.")
    console.print("Type 'quit' to exit.\n")

    try:
        await client.connect(mode="voice", voice_id=voice)
        console.print(f"[dim]Connected. Conversation: {client.conversation_id}[/dim]\n")

        loop = asyncio.get_event_loop()

        while True:
            # Wait for Enter to start recording
            user_input = await loop.run_in_executor(None, input, "[Press Enter to speak] ")
            if user_input.strip().lower() in ("quit", "exit", "/quit", "/exit"):
                break

            # Start recording
            console.print("[red]Recording...[/red] (press Enter to stop)")
            recorder.start()

            # Wait for Enter to stop recording
            await loop.run_in_executor(None, input, "")

            # Stop recording and get PCM data
            pcm_data = recorder.stop()
            if not pcm_data:
                console.print("[yellow]No audio captured.[/yellow]")
                continue

            console.print("[dim]Processing...[/dim]")

            # Convert PCM to WebM for the server
            webm_data = await pcm_to_webm(pcm_data)

            # Send audio and handle response
            full_text = ""
            async for event in client.send_audio(webm_data):
                if isinstance(event, bytes):
                    # Play TTS audio
                    await player.play(event)
                    continue

                event_type = event.get("type", "")
                if event_type == "transcription.final":
                    console.print(f"[dim]You said: {event.get('text', '')}[/dim]")
                elif event_type == "response.text":
                    content = event.get("content", "")
                    full_text += content
                    console.print(content, end="")
                elif event_type == "response.end":
                    if not full_text:
                        full_text = event.get("full_text", "")
                        console.print(full_text)
                    console.print()  # newline
                elif event_type == "error":
                    console.print(f"\n[red]Error: {event.get('message', 'Unknown error')}[/red]")

            console.print()  # blank line between exchanges

    except ConnectionRefusedError:
        console.print("[red]Could not connect to Dolores server. Is it running?[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
    finally:
        await client.close()
        console.print("[dim]Goodbye![/dim]")
