import logging
from typing import Optional
from config import config

class Logger:
    """Centralized logging configuration and utility class."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._setup_logger()
        return cls._instance

    def _setup_logger(self):
        """Initialize and configure the logger."""
        self.logger = logging.getLogger('TelegramBot')
        self.logger.setLevel(getattr(logging, config.log_level))

        # Create console handler with formatting
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(config.log_format))
        self.logger.addHandler(console_handler)

    def info(self, message: str):
        """Log info level message."""
        self.logger.info(message)

    def error(self, message: str, exc: Optional[Exception] = None):
        """Log error level message with optional exception."""
        if exc:
            self.logger.error(f"{message}: {str(exc)}")
        else:
            self.logger.error(message)

    def warning(self, message: str):
        """Log warning level message."""
        self.logger.warning(message)

    def debug(self, message: str):
        """Log debug level message."""
        self.logger.debug(message)

logger = Logger()  # Create a singleton instance