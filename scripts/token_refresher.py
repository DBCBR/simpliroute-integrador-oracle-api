"""Token refresher daemon for Gnexum.

Usage:
  powershell> $env:GNEXUM_TOKEN_REFRESH_INTERVAL_SECONDS=300; python .\scripts\token_refresher.py

This calls `login_and_store()` in a loop and logs results. It is safe to run alongside the polling runner.
"""
import os
import asyncio
import logging
from datetime import datetime

from src.integrations.simpliroute import token_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("token_refresher")

INTERVAL = int(os.getenv("GNEXUM_TOKEN_REFRESH_INTERVAL_SECONDS", "300"))
STOP_ON_FAILURE = os.getenv("GNEXUM_TOKEN_REFRESH_STOP_ON_FAILURE", "0") != "0"


async def main_loop():
    logger.info("Token refresher starting; interval=%s seconds", INTERVAL)
    while True:
        try:
            token = await token_manager.login_and_store()
            if token:
                logger.info("[%s] login_and_store returned a token (len=%d)", datetime.utcnow().isoformat(), len(token))
            else:
                logger.warning("[%s] login_and_store did NOT return a token", datetime.utcnow().isoformat())
                if STOP_ON_FAILURE:
                    logger.error("Stopping refresher due to STOP_ON_FAILURE")
                    return
        except Exception as e:
            logger.exception("Unexpected error in token refresher: %s", e)
            if STOP_ON_FAILURE:
                return
        await asyncio.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Token refresher interrupted by user")
