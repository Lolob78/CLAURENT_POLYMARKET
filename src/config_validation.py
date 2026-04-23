"""Validation de la configuration au startup."""
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger("config_validation")


def validate_config():
    """Valide la config avant de lancer le bot. Fail-fast."""
    errors = []

    # Validation edge_min
    if not (0 < settings.edge_min < 1):
        errors.append(f"❌ edge_min doit être entre 0 et 1, actuellement: {settings.edge_min}")

    # Validation risk_per_trade
    if not (0 < settings.risk_per_trade <= 0.1):
        errors.append(f"❌ risk_per_trade doit être entre 0 et 0.1, actuellement: {settings.risk_per_trade}")

    # Validation max_open_positions
    if settings.max_open_positions < 1:
        errors.append(f"❌ max_open_positions doit être >= 1, actuellement: {settings.max_open_positions}")

    # Validation max_drawdown
    if not (0 < settings.max_drawdown < 1):
        errors.append(f"❌ max_drawdown doit être entre 0 et 1, actuellement: {settings.max_drawdown}")

    # Validation paper_mode (doit être True pour ce MVP)
    if not settings.paper_mode:
        errors.append("❌ CRITICAL: paper_mode DOIT être True pour ce MVP")

    # Afficher les erreurs
    if errors:
        logger.error("config_invalid", errors=errors)
        for error in errors:
            print(error)
        raise ValueError(f"Configuration invalide: {len(errors)} erreur(s)")

    # Log success
    logger.info(
        "config_validated",
        edge_min=settings.edge_min,
        risk_per_trade=settings.risk_per_trade,
        max_open_positions=settings.max_open_positions,
        max_drawdown=settings.max_drawdown,
        paper_mode=settings.paper_mode,
    )
    print("✅ Configuration validée")
