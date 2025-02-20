import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import os
import logging
from apify_client import ApifyClientAsync

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class ApifyConfig:
    """
    Configuration class for Apify settings.
    """
    def __init__(self, api_token: Optional[str] = None, actor_name: str = 'apidojo/tweet-scraper'):
        """
        Initializes ApifyConfig.

        Args:
            api_token: Apify API token. If None, tries to get it from environment variable 'APIFY_TOKEN'.
            actor_name: Name of the Apify actor to use.
        """
        self.api_token = api_token or os.environ.get("APIFY_TOKEN")
        if not self.api_token:
            logging.error("APIFY_TOKEN is not set. Please set it via argument or environment variable.")
        self.actor_name = actor_name


class ApifyService:
    """
    Service class to interact with Apify API.
    """
    def __init__(self, config: ApifyConfig):
        """
        Initializes ApifyService with ApifyConfig.

        Args:
            config: An ApifyConfig instance.
        """
        self.config = config
        self.client: Optional[ApifyClientAsync] = None

    async def initialize_client(self) -> bool:
        """
        Initializes the Apify client.

        Returns:
            bool: True if client initialization is successful, False otherwise.
        """
        if not self.config.api_token:
            return False
        try:
            self.client = ApifyClientAsync(self.config.api_token)
            return True
        except Exception as e:
            logging.error(f"Failed to initialize Apify client: {e}")
            return False

    async def run_actor(self, run_input: Dict) -> Optional[List[Dict]]:
        """
        Runs the Apify actor with the given input.

        Args:
            run_input: Dictionary containing the input for the Apify actor.

        Returns:
            Optional[List[Dict]]: List of dataset items (tweets) or None if actor run fails or client is not initialized.
        """
        if not self.client:
            logging.error("Apify client is not initialized. Call initialize_client() first.")
            return None
        try:
            actor = self.client.actor(self.config.actor_name)
            run = await actor.call(run_input=run_input)

            if not run:
                logging.error("Apify actor run failed.")
                return None

            dataset_client = self.client.dataset(run['defaultDatasetId'])
            result = await dataset_client.list_items()
            return result.items

        except Exception as e:
            logging.error(f"Error occurred while running Apify actor: {str(e)}")
            return None

    async def close_client(self):
        """
        Closes the Apify client.
        """
        if self.client:
            await self.client.close()


class XScraper:
    """
    Organizes scraping operations for X (Twitter).
    """
    def __init__(self, apify_service: ApifyService):
        """
        Initializes XScraper with an ApifyService instance.

        Args:
            apify_service: An ApifyService instance.
        """
        self.apify_service = apify_service

    async def search_tweets_by_keyword(self, keyword: str,  start: str = None, end: str = None, max_results: int = 100) -> List[Dict]:
        """
        Searches tweets by keyword using Apify.

        Args:
            keyword: The keyword to search for.
            max_results: Maximum number of tweets to retrieve.

        Returns:
            List[Dict]: List of tweet dictionaries.
        """
        logging.info(f"Searching tweets for keyword: '{keyword}' (max_results: {max_results})")
        run_input = {
            "searchTerms": [keyword],
            "sort": "Latest",
            "maxItems": max_results,
            "start": start,
            "end": end
        }
        tweets = await self.apify_service.run_actor(run_input)
        return tweets if tweets else []

    async def get_profile_tweets(self, username: str, months_back: int = 12) -> List[Dict]:
        """
        Retrieves tweets from a specific X profile for the last N months.

        Args:
            username: X username (without '@').
            months_back: Number of months of tweet history to fetch.

        Returns:
            List[Dict]: List of tweet dictionaries.
        """
        logging.info(f"Fetching tweets from profile: '{username}' for last {months_back} months.")
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
            "includeSearchTerms": False
        }
        tweets = await self.apify_service.run_actor(run_input)
        return tweets if tweets else []

    def print_tweet_details(self, tweets: List[Dict]):
        """
        Prints specific details for each tweet in the list.

        Args:
            tweets: List of tweet dictionaries.
        """
        if not tweets:
            logging.info("No tweets to print.")
            return

        for tweet in tweets:
            logging.info("-" * 20)
            logging.info(f"ID: {tweet.get('id')}")
            logging.info(f"URL: {tweet.get('url')}")
            logging.info(f"Created At: {tweet.get('createdAt')}")
            logging.info(f"Text: {tweet.get('text')}")
        logging.info("-" * 20)


async def main():
    # 1. Initialize Apify Configuration
    apify_config = ApifyConfig(api_token="apify_api_WQPEHWusVWXt5wSJd2SzSLoDZDDvMf4jqVW2") # You can pass API token and actor name here if needed

    # 2. Initialize Apify Service
    apify_service = ApifyService(apify_config)
    if not await apify_service.initialize_client():
        return  # Exit if client initialization fails

    # 3. Initialize XScraper
    x_scraper = XScraper(apify_service)

    # 4. Example Usage: Search by keyword
    # keyword_tweets = await x_scraper.search_tweets_by_keyword("artificial intelligence", max_results=100)
    # logging.info(f"Found {len(keyword_tweets)} tweets about AI:")
    # x_scraper.print_tweet_details(keyword_tweets)

    # 5. Example Usage: Get profile tweets
    profile_tweets = await x_scraper.get_profile_tweets("elonmusk", months_back=3)
    logging.info(f"\nFound {len(profile_tweets)} tweets from profile:")
    x_scraper.print_tweet_details(profile_tweets)

    # 6. Close Apify Client
    await apify_service.close_client()


if __name__ == "__main__":
    asyncio.run(main())