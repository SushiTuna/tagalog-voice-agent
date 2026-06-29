import asyncio
import logging
import os

from pipeline import create_and_run_bot


async def main():
    """Standalone entry point for running the bot without the FastAPI server."""
    room_url = os.environ.get("DAILY_ROOM_URL")
    if not room_url:
        raise RuntimeError("DAILY_ROOM_URL environment variable is required")

    await create_and_run_bot(room_url=room_url, session_id="standalone")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
