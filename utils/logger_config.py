import logging
from logging.handlers import RotatingFileHandler
import os

class LoggerConfig:
    """Centralized logging configuration for the application."""
    
    def __init__(self, log_level: str = 'INFO', log_format: str = None):
        self.log_level = getattr(logging, log_level.upper())
        self.log_format = log_format or '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        self.log_dir = 'logs'
        self._setup_logging()
    
    def _setup_logging(self):
        """Configure logging with both file and console handlers."""
        # Create logs directory if it doesn't exist
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
            
        # Create formatters
        formatter = logging.Formatter(self.log_format)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)
        
        # Clear any existing handlers
        root_logger.handlers = []
        
        # Create and configure file handler
        file_handler = RotatingFileHandler(
            filename=os.path.join(self.log_dir, 'app.log'),
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(self.log_level)
        
        # Create and configure console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(self.log_level)
        
        # Add handlers to root logger
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        
        # Create logger for this module
        self.logger = logging.getLogger(__name__)
        
    def get_logger(self, name: str) -> logging.Logger:
        """Get a logger instance with the specified name.
        
        Args:
            name: Name for the logger, typically __name__ of the calling module
            
        Returns:
            logging.Logger: Configured logger instance
        """
        return logging.getLogger(name)