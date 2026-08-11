"""Logging centralisé avec structlog."""
import structlog
from pathlib import Path

# Créer le répertoire data s'il n'existe pas
Path("./data").mkdir(exist_ok=True)


def setup_logging(log_file: str = "./data/claurent.log"):
    """Configure structlog."""
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer(),  # ← Simple console output
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__):
    """Récupère un logger structlog nommé."""
    return structlog.get_logger(name)


# Configuration par défaut
setup_logging()
logger = get_logger("claurent")