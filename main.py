import asyncio
import logging

import config
from bot import CGRCBot

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def main():
    if not config.DISCORD_TOKEN:
        raise ValueError(
            "DISCORD_TOKEN is not set. Run `python setup_db.py` to initialise the config database."
        )

    bot = CGRCBot()
    async with bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
