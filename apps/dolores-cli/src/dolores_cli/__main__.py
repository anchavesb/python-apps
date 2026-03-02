"""Entry point for dolores-cli."""

from __future__ import annotations

import argparse
import asyncio


def main() -> None:
    parser = argparse.ArgumentParser(description="Dolores CLI - Personal Assistant")
    sub = parser.add_subparsers(dest="command", help="Command")

    # Text chat subcommand
    chat_cmd = sub.add_parser("chat", help="Interactive text chat")
    chat_cmd.add_argument("--server", help="Server WebSocket URL")
    chat_cmd.add_argument("--api-key", help="API key for authentication")
    chat_cmd.add_argument("--provider", help="LLM provider to use")

    # Voice chat subcommand
    voice_cmd = sub.add_parser("voice", help="Interactive voice chat (push-to-talk)")
    voice_cmd.add_argument("--server", help="Server WebSocket URL")
    voice_cmd.add_argument("--api-key", help="API key for authentication")
    voice_cmd.add_argument("--provider", help="LLM provider to use")
    voice_cmd.add_argument("--voice-id", help="Voice profile ID for TTS")

    args = parser.parse_args()

    if args.command == "voice":
        from .voice_chat import voice_chat_loop

        asyncio.run(
            voice_chat_loop(
                server_url=getattr(args, "server", None),
                api_key=getattr(args, "api_key", None),
                provider=getattr(args, "provider", None),
                voice_id=getattr(args, "voice_id", None),
            )
        )
    elif args.command == "chat" or args.command is None:
        from .chat import chat_loop

        asyncio.run(
            chat_loop(
                server_url=getattr(args, "server", None),
                api_key=getattr(args, "api_key", None),
                provider=getattr(args, "provider", None),
            )
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
