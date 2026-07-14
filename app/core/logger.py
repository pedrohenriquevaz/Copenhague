from __future__ import annotations

import logging
import sys

from app.core.config import get_settings


def setup_logging() -> None:
    settings = get_settings()
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(name)s | "
                "process=%(process)d thread=%(threadName)s | %(message)s"
            )
        )
        root.addHandler(handler)

    network_level = getattr(
        logging,
        settings.NETWORK_LOG_LEVEL,
        logging.INFO,
    )
    logging.getLogger("app.network.access").setLevel(network_level)
    logging.getLogger("app.integrations").setLevel(network_level)
    logging.getLogger("discord.gateway").setLevel(network_level)
    # O trace seguro da aplicacao registra acesso sem payloads ou tokens.
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.client").setLevel(logging.WARNING)
