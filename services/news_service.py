import json
import re
from typing import List, Dict, Optional
from datetime import datetime
from openai import OpenAI
import requests
from smolagents import CodeAgent, OpenAIServerModel, tool
from config.settings import settings
from utils.utils import OpenAIService
from config.prompt import get_news_prompt

logger = settings.get_logger(__name__)


    

class NewsService:
    """Service class for news-related operations."""
    openai_service = OpenAIService()
    def __init__(self):

        self.setup_tools()
        
    @staticmethod
    @tool
    def llm_chat(prompt: str) -> str:
        """
        Use this tool to chat with the LLM. To do tasks like translation, summarization, text generation, extraction, etc.

        Args:
            prompt: The prompt to send to the LLM.

        Returns:
            The response from the LLM.
        """
        client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url
        )
        response = client.chat.completions.create(
            model="gemini-2.0-flash-001",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    
    @staticmethod
    @tool
    def translate_to_chinese(text: str) -> str:
        """
        Use this tool to translate the text to Chinese.

        Args:
            text: The text to translate to Chinese.

        Returns:
            The translated text.
        """
        return NewsService.llm_chat(
        f"Translate the following text to Chinese: {text} Output the translation directly."
    )

    @staticmethod
    @tool
    def summarize_in_chinese(text: str) -> str:
        """
        Use this tool to summarize the text in Chinese.

        Args:
            text: The text to summarize.

        Returns:
            The summarized text.
        """
        return NewsService.llm_chat(
            f"Summarize the following text in Chinese: {text} Output the summary directly. The summary should be concise and only include the most important information."
        )

    @tool
    def get_news_concept_suggestion(keyword: str) -> List[str]:
        """
        Get concept suggestions from EventRegistry API based on a keyword prefix, Call this tool to get the concept suggestions before calling get_news. The keyword must be in English.

        Args:
            keyword: Keyword to search for

        Returns:
            list: List of suggested concepts string, for example: ["uri-1", "uri-2", "uri-3"]

        Raises:
            Exception: If unable to fetch suggestions
        """
        try:
            response = requests.get(
                "https://eventregistry.org/api/v1/suggestConceptsFast",
                params={
                    "prefix": keyword,
                    "lang": "eng",
                    "apiKey": settings.eventregistry_key
                }
            )
            response.raise_for_status()
            data = response.json()
            return [item['uri'] for item in data[:1]]
        except Exception as e:
            logger.error(f"Failed to fetch concept suggestions: {e}")
            raise
    
    def get_news(self, topic: str, date: str):
        return self.agent.run(task=get_news_prompt.replace('{sourceUris}', str(settings.sourceUris)).replace('{topic}', topic).replace('{date}', date))

    def setup_tools(self):
        """Setup CodeAgent with necessary tools."""
        self.agent = CodeAgent(
            tools=[
                self.get_news_concept_suggestion,
                self.translate_to_chinese,
                self.summarize_in_chinese
            ],
            model=NewsService.openai_service.model,
            additional_authorized_imports=["requests", "eventregistry", "datetime", "json"]
        )
        
