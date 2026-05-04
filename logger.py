"""
Logging Configuration
Replaces print statements with structured logging
"""

import logging
import logging.handlers
import os
from datetime import datetime
from typing import Optional

# On Vercel the repo root is read-only; /tmp is the only writable path
_LOG_DIR = '/tmp/logs' if os.environ.get('VERCEL') else 'logs'
os.makedirs(_LOG_DIR, exist_ok=True)


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output"""

    grey = "\x1b[38;21m"
    blue = "\x1b[38;5;39m"
    yellow = "\x1b[38;5;226m"
    red = "\x1b[38;5;196m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"

    FORMATS = {
        logging.DEBUG: grey + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + reset,
        logging.INFO: blue + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + reset,
        logging.WARNING: yellow + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + reset,
        logging.ERROR: red + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + reset,
        logging.CRITICAL: bold_red + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt='%H:%M:%S')
        return formatter.format(record)


def setup_logger(
    name: str,
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    console: bool = True
) -> logging.Logger:
    """
    Setup a logger with file and console handlers

    Args:
        name: Logger name (usually __name__)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path
        console: Whether to output to console

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Remove existing handlers
    logger.handlers = []

    # File handler with rotation
    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    # Console handler with colors
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(ColoredFormatter())
        logger.addHandler(console_handler)

    return logger


def setup_app_logger(app, log_level: str = 'INFO') -> logging.Logger:
    """
    Setup application-wide logger

    Args:
        app: Flask application instance
        log_level: Log level as string (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Application logger
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Main app logger
    app_logger = setup_logger(
        'valuation_app',
        level=level,
        log_file=f'{_LOG_DIR}/app.log',
        console=True
    )

    # Database logger
    db_logger = setup_logger(
        'valuation_app.database',
        level=level,
        log_file=f'{_LOG_DIR}/database.log',
        console=False
    )

    # API logger
    api_logger = setup_logger(
        'valuation_app.api',
        level=level,
        log_file=f'{_LOG_DIR}/api.log',
        console=False
    )

    # Valuation logger
    valuation_logger = setup_logger(
        'valuation_app.valuation',
        level=level,
        log_file=f'{_LOG_DIR}/valuation.log',
        console=False
    )

    # Security logger (always log to file)
    security_logger = setup_logger(
        'valuation_app.security',
        level=logging.INFO,
        log_file=f'{_LOG_DIR}/security.log',
        console=False
    )

    # Configure Flask app logger
    app.logger.handlers = []
    for handler in app_logger.handlers:
        app.logger.addHandler(handler)
    app.logger.setLevel(level)

    app_logger.info("=" * 60)
    app_logger.info("Application logging initialized")
    app_logger.info(f"Log level: {log_level}")
    app_logger.info(f"Log directory: {_LOG_DIR}/")
    app_logger.info("=" * 60)

    return app_logger


def log_api_request(logger: logging.Logger, method: str, endpoint: str, status: int, duration: float):
    """Log API request"""
    logger.info(
        f"{method} {endpoint} - {status} - {duration:.2f}ms",
        extra={
            'method': method,
            'endpoint': endpoint,
            'status': status,
            'duration_ms': duration
        }
    )


def log_valuation(logger: logging.Logger, company_id: int, company_name: str, result: dict):
    """Log valuation calculation"""
    logger.info(
        f"Valuation completed for {company_name} (ID: {company_id})",
        extra={
            'company_id': company_id,
            'company_name': company_name,
            'fair_value': result.get('final_equity_value'),
            'recommendation': result.get('recommendation')
        }
    )


def log_security_event(logger: logging.Logger, event_type: str, user: str, details: str):
    """Log security-related events"""
    logger.warning(
        f"Security Event: {event_type} - User: {user} - {details}",
        extra={
            'event_type': event_type,
            'user': user,
            'details': details,
            'timestamp': datetime.now().isoformat()
        }
    )


def log_database_query(logger: logging.Logger, query: str, duration: float, rows_affected: int = 0):
    """Log database queries"""
    logger.debug(
        f"Query executed in {duration:.2f}ms - {rows_affected} rows affected",
        extra={
            'query': query[:100],  # Truncate long queries
            'duration_ms': duration,
            'rows_affected': rows_affected
        }
    )


# Convenience function to get logger
def get_logger(name: str = 'valuation_app') -> logging.Logger:
    """Get or create a logger"""
    return logging.getLogger(name)


# Example usage for different modules
if __name__ == '__main__':
    # Setup loggers
    app_logger = setup_logger('valuation_app', logging.DEBUG, 'logs/test.log')

    # Test different log levels
    app_logger.debug("This is a debug message")
    app_logger.info("This is an info message")
    app_logger.warning("This is a warning message")
    app_logger.error("This is an error message")
    app_logger.critical("This is a critical message")

    print("\n✅ Logging test complete! Check logs/test.log")
