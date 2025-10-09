# src/common/logging.py
import logging
import sys

import structlog


def configure_logging(log_level: str = "INFO"):
    """Configures structured, JSON-formatted logging for the application.

    This setup uses structlog to create logs that are easy to parse and
    filter in a production environment.

    Args:
        log_level: The minimum log level to output (ie "INFO", "DEBUG").
    """
    logging.basicConfig(
        level=log_level,
        stream=sys.stdout,
        format="%(message)s",
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
