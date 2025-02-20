import os
from typing import Optional
from utils.logger_config import LoggerConfig
from dotenv import load_dotenv
import logging

class Settings:
    """Centralized configuration settings for the application."""
    
    def __init__(self):
        load_dotenv()
        
        # Initialize logger
        self.logger_config = LoggerConfig(
            log_level=os.environ.get('LOG_LEVEL', 'INFO'),
            log_format=os.environ.get('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )
        self.logger = self.logger_config.get_logger(__name__)
        
        logging.getLogger('smolagents').setLevel(logging.WARNING)
        logging.getLogger('httpx').setLevel(logging.WARNING)
        
        # Telegram Bot Configuration
        self.telegram_token: str = os.environ.get('TELEGRAM_TOKEN')
        if not self.telegram_token:
            self.logger.warning("TELEGRAM_TOKEN not set in environment variables")
        
        # OpenAI Configuration
        self.openai_api_key: str = os.environ.get('OPENAI_API_KEY')
        self.openai_base_url: str = os.environ.get('OPENAI_BASE_URL', 'https://concept.dica.cc/llm')
        if not self.openai_api_key:
            self.logger.warning("OPENAI_API_KEY not set in environment variables")
        
        # Apify Configuration
        self.apify_token: str = os.environ.get('APIFY_TOKEN')
        self.apify_actor: str = os.environ.get('APIFY_ACTOR', 'apidojo/tweet-scraper')
        if not self.apify_token:
            self.logger.warning("APIFY_TOKEN not set in environment variables")
        
        # EventRegistry Configuration
        self.eventregistry_key: str = os.environ.get('EVENTREGISTRY_KEY')
        if not self.eventregistry_key:
            self.logger.warning("EVENTREGISTRY_KEY not set in environment variables")
        
        # Model Configuration
        self.model_id: str = os.environ.get('MODEL_ID', 'gemini-2.0-flash-001')
        
        news_sources = [
    "bbc.com",
    "cnn.com",
    "wsj.com",
    "voanews.com",
    "abcnews.go.com",
    "rfa.org",
    "bloomberg.com",
    "cbsnews.com",
    "forbes.com",
    "nbcnews.com",
    "nytimes.com",
    "foxnews.com",
    "politico.com",
    "foreignaffairs.com",
    "thehill.com",
    "washingtontimes.com",
    "hosted.ap.org",
    "reuters.com",
    "nhk.or.jp",
    "rfi.fr",
    "interfax.com",
    "tass.com",
    "aljazeera.com",
    "yna.co.kr",
    "scmp.com",
    "ft.com",
    "dw.com",
    "theguardian.com",
    "smh.com.au",
    "voachinese.com",
    "cn.rfi.fr",
    "cn.nytimes.com",
    "cn.reuters.com",
    "cn.nikkei.com",
    "cn.wsj.com",
    "china.kyodonews.net",
    "news.bbc.co.uk",
    "sputniknews.cn",
    "cn.inform.kz",
    "chinese.yonhapnews.co.kr",
    "ftchinese.com",
    "zaobao.com.sg",
    "chinese.joins.com",
    "china.hani.co.kr",
    "asahi.com",
    "nzherald.co.nz",
    "chinese.aljazeera.net",
    "abc.net.au",
    "theguardian.com",
    "cn.theaustralian.com.au",
    "hk01.com",
    "chinatimes.com",
    "ltn.com.tw",
    "taiwandaily.net",
    "wenweipo.com",
    "takungpao.com",
    "udn.com",
    "news.mingpao.com",
    "china.hket.com",
    "cna.com.tw",
    "tw.news.yahoo.com",
    "setn.com",
    "sinchew.com.my",
    "hk.on.cc",
    "std.stheadline.com",
    "news.ebc.net.tw",
    "health.tvbs.com.tw",
    "news.yahoo.com",
    "dwnews.com",
    "ntdtv.com",
    "secretchina.com",
    "rfa.org",
    "epochtimes.com",
    "soundofhope.org",
    "greetings.minghui.org",
    "qikan.minghui.org",
    "washingtonpost.com",
    "nhk.or.jp",
    "imnews.imbc.com",
    "yna.co.kr",
    "lemonde.fr",
    "postkhmer.com",
    "yomiuri.co.jp",
    "matichon.co.th",
    "leparisien.fr",
    "clarin.com",
    "excelsior.com.mx",
    "interfax.ru",
    "bharian.com.my",
    "info.51.ca"
]
        self.sourceUris: list = [{"sourceUri": sourceUri} for sourceUri in news_sources]
        
    @property
    def is_valid(self) -> bool:
        """Check if all required configuration values are set."""
        return all([
            self.telegram_token,
            self.openai_api_key,
            self.apify_token,
            self.eventregistry_key
        ])
    
    def get_logger(self, name: str) -> Optional[object]:
        """Get a configured logger instance.
        
        Args:
            name: Name for the logger, typically __name__ of the calling module
            
        Returns:
            Optional[object]: Configured logger instance or None if logger config is not initialized
        """
        return self.logger_config.get_logger(name) if self.logger_config else None

# Create a global settings instance
settings = Settings()