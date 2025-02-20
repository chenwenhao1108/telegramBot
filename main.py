import signal
import sys
from services.bot_service import TelegramBotService
from config.settings import settings

logger = settings.get_logger(__name__)

def handle_shutdown(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}. Initiating shutdown...")
    sys.exit(0)

def main():
    """Main entry point for the Telegram bot application."""
    try:
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)

        # Initialize and run the bot service
        logger.info("Initializing Telegram bot service...")
        telegram_token = settings.telegram_token
        bot_service = TelegramBotService(telegram_token)
        bot_service.run()

    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()