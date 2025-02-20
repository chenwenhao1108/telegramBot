import asyncio
from datetime import datetime, timedelta
from pprint import pprint
from typing import List, Dict, Optional
import logging
from apify_client import ApifyClientAsync
from config.settings import settings

logger = settings.get_logger(__name__)

class ApifyConfig:
    """Configuration class for Apify settings."""
    def __init__(self, api_token: Optional[str] = None, actor_name: str = None):
        """Initialize ApifyConfig with API token and actor name."""
        self.api_token = api_token or settings.apify_token
        self.actor_name = actor_name or settings.apify_actor
        if not self.api_token:
            logger.error("APIFY_TOKEN is not set. Please set it via argument or environment variable.")

class ApifyService:
    """Service class to interact with Apify API."""
    def __init__(self, config: ApifyConfig):
        self.config = config
        self.client: Optional[ApifyClientAsync] = None

    async def initialize_client(self) -> bool:
        """Initialize the Apify client."""
        if not self.config.api_token:
            logger.error("Missing Apify API token")
            return False
        try:
            self.client = ApifyClientAsync(self.config.api_token)
            logger.info("Successfully initialized Apify client")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Apify client: {e}")
            return False

    async def run_actor(self, run_input: Dict) -> Optional[List[Dict]]:
        """Run the Apify actor with the given input."""
        if not self.client:
            logger.error("Apify client is not initialized. Call initialize_client() first.")
            return None
        try:
            actor = self.client.actor(self.config.actor_name)
            logger.info(f"Running Apify actor: {self.config.actor_name}")
            run = await actor.call(run_input=run_input)

            if not run:
                logger.error("Apify actor run failed.")
                return None

            dataset_client = self.client.dataset(run['defaultDatasetId'])
            result = await dataset_client.list_items()
            logger.info(f"Successfully retrieved {len(result.items)} items from Apify dataset")
            return result.items

        except Exception as e:
            logger.error(f"Error occurred while running Apify actor: {str(e)}")
            return None

    async def close_client(self):
        """Close the Apify client."""
        if self.client:
            await self.client.close()
            logger.info("Apify client closed")

class XScraper:
    """Service class for X (Twitter) scraping operations."""
    def __init__(self, apify_service: ApifyService):
        self.apify_service = apify_service

    async def search_tweets_by_keyword(self, keyword: str, start: str = None, end: str = None, max_results: int = 51) -> List[Dict]:
        """Search tweets by keyword using Apify."""
        logger.info(f"Searching tweets for keyword: '{keyword}' (max_results: {max_results})")
        run_input = {
            "searchTerms": [keyword],
            "sort": "Latest",
            "maxItems": max_results,
            "start": start,
            "end": end
        }
        tweets = await self.apify_service.run_actor(run_input)
        return tweets if tweets else []

    async def get_profile_tweets(self, username: str, months_back: int = 3, max_results: int = 51) -> List[Dict]:
        """Retrieve tweets from a specific X profile."""
        logger.info(f"Fetching tweets from profile: '{username}' for last {months_back} months")
        end_date = datetime.now()
        search_terms = []

        for i in range(months_back):
            end = end_date - timedelta(days=i*30)
            start = end - timedelta(days=30)
            search_terms.append(
                f"from:{username} since:{start.strftime('%Y-%m-%d')} until:{end.strftime('%Y-%m-%d')}"
            )

        run_input = {
            "searchTerms": search_terms,
            "sort": "Latest",
            "includeSearchTerms": False,
            "maxItems": max_results,
        }
        tweets = await self.apify_service.run_actor(run_input)
        return tweets if tweets else []

    def format_tweet_details(self, tweets: List[Dict]) -> List[str]:
        """Format tweet details for output."""
        if not tweets:
            logger.info("No tweets to format")
            return []

        formatted_tweets = []
        for tweet in tweets:
            formatted_tweet = (
                f"# Tweet Details\n"
                f"- ID: {tweet.get('id')}\n"
                f"- URL: {tweet.get('url')}\n"
                f"- Created At: {tweet.get('createdAt')}\n"
                f"- Text: {tweet.get('text')}"
            )
            formatted_tweets.append(formatted_tweet)
            
        return formatted_tweets
    
    
async def main():
    x_scraper = XScraper(ApifyService(ApifyConfig()))
    tweets = await x_scraper.get_profile_tweets("elonmusk", months_back=3)
    pprint(tweets)

  
if __name__ == "__main__":
    asyncio.run(main())