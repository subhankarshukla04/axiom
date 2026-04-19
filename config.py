"""
Database Configuration
Handles PostgreSQL and SQLite connections
"""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Base configuration"""

    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # Database settings
    DATABASE_TYPE = os.environ.get('DATABASE_TYPE', 'sqlite')  # 'sqlite' or 'postgresql'

    # PostgreSQL settings
    POSTGRES_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
    POSTGRES_PORT = os.environ.get('POSTGRES_PORT', '5432')
    POSTGRES_DB = os.environ.get('POSTGRES_DB', 'valuations_institutional')
    POSTGRES_USER = os.environ.get('POSTGRES_USER', os.environ.get('USER', 'postgres'))
    POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', '')

    # SQLite settings (fallback)
    SQLITE_DB = 'valuations.db'

    # Session settings
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour

    # Security settings
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    # Rate limiting
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URL = 'memory://'  # Use Redis in production

    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = 'logs/app.log'

    # Recommendation thresholds (percentages)
    RECOMMENDATION_THRESHOLDS = {
        'strong_buy': float(os.environ.get('THRESH_STRONG_BUY', '20')),  # >= 20%
        'buy': float(os.environ.get('THRESH_BUY', '10')),                # >= 10%
        'hold': float(os.environ.get('THRESH_HOLD', '-10')),             # > -10% and <= 10%
        'underweight': float(os.environ.get('THRESH_UNDERWEIGHT', '-20'))# > -20% and <= -10%
    }

    # Valuation method weights (sum should be 1.0)
    # Default changed to use DCF as the primary/display fair value method.
    VALUATION_WEIGHTS = {
        'dcf': float(os.environ.get('WEIGHT_DCF', '1.0')),
        'ev_ebitda': float(os.environ.get('WEIGHT_EV_EBITDA', '0.0')),
        'pe': float(os.environ.get('WEIGHT_PE', '0.0'))
    }

    # Which method to display as the primary 'Fair Value' in lists/detail cards
    FAIR_DISPLAY_METHOD = os.environ.get('FAIR_DISPLAY_METHOD', 'dcf')  # 'dcf'|'composite'|'ev_ebitda'|'pe'

    # Bear/Bull multipliers for quick scenario buckets
    BEAR_MULTIPLIER = float(os.environ.get('BEAR_MULTIPLIER', '0.75'))
    BULL_MULTIPLIER = float(os.environ.get('BULL_MULTIPLIER', '1.25'))

    # Monte Carlo defaults (volatility inputs)
    MONTE_CARLO_GROWTH_VOL = float(os.environ.get('MONTE_GROWTH_VOL', '0.15'))
    MONTE_CARLO_DISCOUNT_VOL = float(os.environ.get('MONTE_DISCOUNT_VOL', '0.10'))

    # Safety margins and overrides
    TERMINAL_MARGIN = float(os.environ.get('TERMINAL_MARGIN', '0.01'))
    ALT_ZSCORE_SELL_THRESHOLD = float(os.environ.get('ALT_ZSCORE_SELL_THRESHOLD', '1.81'))
    DEBT_EQUITY_DOWNGRADE = float(os.environ.get('DEBT_EQUITY_DOWNGRADE', '2.0'))
    # Valuation accuracy guardrails
    TERMINAL_GROWTH_MAX = 0.035   # 3.5% ceiling
    TERMINAL_GROWTH_MIN = 0.005   # 0.5% floor
    WACC_MIN = 0.05               # 5% floor
    WACC_MAX = 0.25               # 25% ceiling
    BETA_FALLBACK_WINDOW = '3y'   # Retry window if 5yr beta fails

    # External Data API Keys (all free tiers)
    FRED_API_KEY = os.environ.get('FRED_API_KEY', '')           # fred.stlouisfed.org
    FINNHUB_API_KEY = os.environ.get('FINNHUB_API_KEY', '')     # finnhub.io (60 calls/min free)
    FMP_API_KEY = os.environ.get('FMP_API_KEY', '')             # financialmodelingprep.com (250/day free)


    @staticmethod
    def get_db_connection_string() -> str:
        """Get database connection string based on DATABASE_TYPE"""
        if Config.DATABASE_TYPE == 'postgresql':
            if Config.POSTGRES_PASSWORD:
                return (
                    f"host={Config.POSTGRES_HOST} "
                    f"port={Config.POSTGRES_PORT} "
                    f"dbname={Config.POSTGRES_DB} "
                    f"user={Config.POSTGRES_USER} "
                    f"password={Config.POSTGRES_PASSWORD}"
                )
            else:
                return (
                    f"host={Config.POSTGRES_HOST} "
                    f"port={Config.POSTGRES_PORT} "
                    f"dbname={Config.POSTGRES_DB} "
                    f"user={Config.POSTGRES_USER}"
                )
        else:
            return Config.SQLITE_DB

    @staticmethod
    def get_db_uri() -> str:
        """Get SQLAlchemy-style database URI"""
        if Config.DATABASE_TYPE == 'postgresql':
            if Config.POSTGRES_PASSWORD:
                return (
                    f"postgresql://{Config.POSTGRES_USER}:{Config.POSTGRES_PASSWORD}@"
                    f"{Config.POSTGRES_HOST}:{Config.POSTGRES_PORT}/{Config.POSTGRES_DB}"
                )
            else:
                return (
                    f"postgresql://{Config.POSTGRES_USER}@"
                    f"{Config.POSTGRES_HOST}:{Config.POSTGRES_PORT}/{Config.POSTGRES_DB}"
                )
        else:
            return f"sqlite:///{Config.SQLITE_DB}"


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    WTF_CSRF_ENABLED = False
    DATABASE_TYPE = 'sqlite'
    SQLITE_DB = ':memory:'


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config(env: Optional[str] = None) -> Config:
    """Get configuration based on environment"""
    if env is None:
        env = os.environ.get('FLASK_ENV', 'development')
    return config.get(env, config['default'])
