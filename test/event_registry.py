import asyncio
import json
import re
from typing import Dict, List
import requests
from openai import OpenAI
from smolagents import CodeAgent, OpenAIServerModel, tool
from datetime import datetime
from pprint import pprint
from eventregistry import *
                                                                                                                                                                                                                                                            
concept_uris = ["http://en.wikipedia.org/wiki/China"]                                                                                                                                                                                      

er = EventRegistry(apiKey="865f8e66-a90a-401c-baf9-e0801e9bd07c")
query = {
  "$query": {
    "$and": [
      {
        "$and": [{"conceptUri": uri} for uri in concept_uris]
      },
      {
        "categoryUri": "news/Politics"
      },
      {
        "dateStart": "2025-01-31", # Set the time window according to the task; if not specified, default to the last 30 days, if specified in the recent 1 hour, you should set the dateStart and dateEnd to the date of today as YYYY-MM-DD format.
        "dateEnd": "2025-02-20",
      },
      {
          "$or": [
              {"lang": "eng"},
              {"lang": "zho"}
          ]
      }
    ]
  },
  "$filter": {
    "isDuplicate": "skipDuplicates"
  }
}
q = QueryArticlesIter.initWithComplexQuery(query)
news_list = []

# change maxItems to get the number of results that you want
for article in q.execQuery(er, maxItems=1):
    pprint(article)