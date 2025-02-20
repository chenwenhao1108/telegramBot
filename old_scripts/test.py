import asyncio
import json
import re
from typing import Dict, List
import requests
from openai import OpenAI
from smolagents import CodeAgent, OpenAIServerModel, tool
from x_scraper import ApifyConfig, ApifyService, XScraper
from datetime import datetime
from pprint import pprint


client = OpenAI(
    api_key="sk-oqUtX7hvjlEsS3VO4dEa14487cE04dA7A7EdF4E492150809",
    base_url="https://concept.dica.cc/llm",
)

model = OpenAIServerModel(
    model_id="gemini-2.0-flash-001",
    api_base="https://concept.dica.cc/llm",
    api_key="sk-oqUtX7hvjlEsS3VO4dEa14487cE04dA7A7EdF4E492150809",
)


@tool
def llm_chat(prompt: str) -> str:
    """
    Use this tool to chat with the LLM. To do tasks like translation, summarization, text generation, extraction, etc.

    Args:
        prompt: The prompt to send to the LLM.

    Returns:
        The response from the LLM.
    """
    response = client.chat.completions.create(
        model="gemini-2.0-flash-001",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


@tool
def translate_to_chinese(text: str) -> str:
    """
    Use this tool to translate the text to Chinese.

    Args:
        text: The text to translate to Chinese.

    Returns:
        The translated text.
    """
    return llm_chat(
        f"Translate the following text to Chinese: {text} Output the translation directly."
    )


@tool
def summarize_in_chinese(text: str) -> str:
    """
    Use this tool to summarize the text in Chinese.

    Args:
        text: The text to summarize.

    Returns:
        The summarized text.
    """
    return llm_chat(
        f"Summarize the following text in Chinese: {text} Output the summary directly. The summary should be concise and only include the most important information."
    )


@tool
def get_news_concept_suggestion(keyword: str) -> list:
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
                "apiKey": "865f8e66-a90a-401c-baf9-e0801e9bd07c",
            },
        )
        response.raise_for_status()
        data = response.json()
        uris = [item['uri'] for item in data[:1]]
        return uris

    except Exception as e:
        raise Exception(f"Failed to fetch concept suggestions: {str(e)}")


@tool
def get_news_source_suggestions(keyword: str) -> list:
    """
    Get news source suggestions from EventRegistry API based on a keyword. You should input short keywords such as BBC, CNN, etc, not BBC News, CNN News, etc.

    Args:
        keyword: Source name to search for

    Returns:
        list: List of suggested news sources with their details

    Raises:
        Exception: If unable to fetch suggestions
    """
    try:
        response = requests.get(
            "https://eventregistry.org/api/v1/suggestSourcesFast",
            params={
                "prefix": keyword,
                "lang": "eng",
                "apiKey": "865f8e66-a90a-401c-baf9-e0801e9bd07c",
            },
        )
        response.raise_for_status()
        data = response.json()

        return data

    except Exception as e:
        raise Exception(f"Failed to fetch source suggestions: {str(e)}")
    


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

sourceUris = [{"sourceUri": sourceUri} for sourceUri in news_sources]
news_prompt = """
You are a news assistant. You are given a task to find news articles about a specific topic. You need to first extract the keywords from the task, for example: when the task is "Shigeru Ishiba     
  visit China", you should extract a list like ["Shigeru Ishiba", "China"](every keyword must be English), then you need to use the get_news_concept_suggestion tool (the input must be in English) for every single keyword to get a concept list (**The return value of this tool is a list of string like ["uri-1", "uri-1", "uri-3"]**, so you can just merge all the list from every keyword into a whole list). You can also use the get_news_source_suggestions tool to get the news sources to search for only when the user requests, else using the news sources form the example code. Then search for news. You should only call the news api once. Do not do multi turn. After you get the news, you need to make sure the news is relevant to the topic. If it is not, do not return the news.
Here's how to use the news api to fetch news: 
**You need to set the time window according to the task, for example: if the task is "今天有哪些关于中国的新闻？", you should set the time window to today.if not specified, default to the last 30 days.**

```python
keywords = ["keyword1", "keyword2"]                                                                                                                                                                                                                                                               
concept_uris = []                                                                                                                                                                                                                                                                                                   
for keyword in keywords:                                                                                                                                                                                                                                                                                 
    concept_suggestions = get_news_concept_suggestion(keyword=keyword)                                                                                                                                                                                                                                   
    if concept_suggestions:                                                                                                                                                                                                                                                         
        concept_uris.extend(concept_suggestions)                                                                                                                                                                                        
                                                                                                                                                                                                                                                                                                        
print(f"Concept URIs: {concept_uris}")

er = EventRegistry(apiKey=865f8e66-a90a-401c-baf9-e0801e9bd07c)
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
        "$or": {sourceUris}
      },
      {
        "dateStart": "2025-01-31", # Set the time window according to the task; if not specified, default to the last 30 days.
        "dateEnd": "2025-02-07",
      },
      {
          $or: [
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
for article in q.execQuery(er, maxItems=30):
    title = translate_to_chinese(article["title"])
    date = article["date"] + " " + article["time"]
    url = article["url"]
    source = article["source"]["title"]
    summary = summarize_in_chinese(article["body"])
    output = f"# {title}\n- 日期：{date}\n- 来源：{source}\n- 链接：{url}\n- 摘要：{summary}"
    news_list.append(output)
    
```
When you are done, you should **return a list of news in Markdown format**, including the title, date, link, source and summary. You need to make sure the result news are really relevant to the user query. Filter out the news that are not relevant.

Output all contents in Chinese.

The task is {topic}, today is {date}.

Example output:
[
"# 习近平访问美国
- 日期：2025-01-31
- 来源：BBC
- 链接：https://www.bbc.com/news/world-us-canada-1234567890
- 摘要：习近平访问美国，与拜登总统会谈，讨论中美关系和全球问题。",

"# 习近平访问美国
- 日期：2025-01-31
- 来源：BBC
- 链接：https://www.bbc.com/news/world-us-canada-1234567890
- 摘要：习近平访问美国，与拜登总统会谈，讨论中美关系和全球问题。",
]

请确保你的输出符合这个格式，且为中文
""".replace('{sourceUris}', str(sourceUris))

news_agent = CodeAgent(
    tools=[
        get_news_concept_suggestion,
        get_news_source_suggestions,
        translate_to_chinese,
        summarize_in_chinese,
    ],
    model=model,
    additional_authorized_imports=["requests", "eventregistry", "datetime", "json"],
)


analyze_news_system_prompt = """
你是一个文本内容分析师，擅长对文本内容进行分析总结，并根据总结回答用户提问。
"""

analyze_news_prompt = """
下面是一个{task_type}列表，请总结这个列表里的{task_type}内容，并回答用户提问。
{task_type}列表：
{news_list}

用户提问：
{user_question}
"""

def gpt_infer(user_prompt, model_client=client, model="gemini-2.0-flash-thinking-exp-01-21", system_prompt=analyze_news_system_prompt, temperature=0.6):
    retries = 3
    for _ in range(retries):
        try:
            completion = model_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system",
                    "content": system_prompt},
                    {"role": "user",
                    "content": user_prompt}
                ],
                timeout=300,
                temperature=temperature,
            )
            res_raw = completion.choices[0].message.content
            pattern = re.compile(r'```json\s*([\s\S]*?)\s*```')
            matches = pattern.findall(res_raw)
            if len(matches) > 0:
                json_str = matches[0]
                print("原始 JSON 字符串:\n", json_str)
                try:
 
                    parsed_data = json.loads(json_str, strict=False)
                    return parsed_data
                except json.JSONDecodeError as e:
                    print("JSON Decode Error:", e)
                    return res_raw
            else:
                return res_raw
        except Exception as e:
            print(f"Ask openai in json api call failed: {e}")
            continue


analyze_posts_prompt = """
你是一个专业的翻译和总结专家，能够对社媒帖子内容进行准确的总结和翻译，下面我将会给你一个列表的围绕关键词：{keywords}的推特帖子，每个列表元素的结构为：{"url": "https://www.x.com/post/1", "date": "2025-2-13", "content": "This is the content of the post."}

**请你按照以下步骤进行分析：**
1. 分析每个帖子的content字段内容
2. 对每个帖子内容进行总结和翻译
3. 判断帖子内容是否同时与关键词： {keywords} 有关
4. 选取在第三步中判断为有关的帖子，并返回一个类似于下面结构的列表，**每个列表元素都是和下面示例中一样结构的字符串**

Example output:

```json
["# 习近平访问美国\n- 日期：2025-01-31\n- 链接：https://www.bbc.com/news/world-us-canada-1234567890\n- 内容：习近平访问美国，与拜登总统会谈，讨论中美关系和全球问题。",
"# 习近平访问美国\n- 日期：2025-01-31\n- 链接：https://www.bbc.com/news/world-us-canada-1234567890\n- 内容：习近平访问美国，与拜登总统会谈，讨论中美关系和全球问题。"]
```

**请确保你的输出符合这个格式，且为中文， 并且不要添加任何多余内容和注释**

帖子列表：
{posts_list}
"""

async def get_x_posts(query: str, date: str, max_results: int = 30) -> List[Dict]:
    """
    Get A list of X posts.

    Args:
        keywords: List of keywords to search for
        max_results: Maximum number of results to return

    Returns:
        list: A list of X posts with details like: [{"url": "https://www.x.com/post/1", "date": "2025-2-13", "content": "This is the content of the post."}, ...]

    Raises:
        Exception: If unable to initialize Apify Service
    """
    analyze_query_prompt = f"""
    **请按如下步骤执行任务：**
    1. 分析下面query，通过query理解用户的想要查找的内容
    2. 从用户想要查找的内容中提取**一个列表的英文关键词**， 关键词请保持简单扼要，关键词数量请保持在一到两个左右，例如：当query为：“今天有哪些关于中国的新闻”，关键词列表应为["China"]
    3. 根据用户query，分别生成startDate和endDate，**startDate至少比endDate提前一天**，例如：当query为：“今天有哪些关于中国的新闻”，startDate和endDate应为今天和前一天的日期字符串，如：startDate: 'YYYY-MM-DD'(昨天日期)，endDate: 'YYYY-MM-DD'(今天日期), 以此类推。**如果用户query中并没有表达日期范围,请分别赋值为空字符串**
    4. 请严格保证startDate和endDate的值为YYYY-MM-DD类型的字符串，并严格保证startDate小于endDate
    
    query：
    {query}
    
    今天的日期为：{date}
    
    Example output:
    ```json
    {{
        "keywords": ["keywords1", "keywords2"],
        "startDate": "YYYY-MM-DD",
        "endDate": "YYYY-MM-DD"
    }}
    ```
    
    **请严格按照上面json格式返回，不要返回任何多余内容或注释**
    """
    analysis_result = gpt_infer(user_prompt=analyze_query_prompt, system_prompt='你是一个关键词提取大师')
    pprint(f'用户query分析结果：\n{analysis_result}')
    
    keywords = analysis_result.get("keywords")
    start = analysis_result.get('startDate')
    end = analysis_result.get('endDate')
    
    if not isinstance(keywords, list):
        keywords = [keywords]
    
    # 1. Initialize Apify Configuration
    apify_config = ApifyConfig(api_token="apify_api_WQPEHWusVWXt5wSJd2SzSLoDZDDvMf4jqVW2") # You can pass API token and actor name here if needed

    # 2. Initialize Apify Service
    apify_service = ApifyService(apify_config)
    if not await apify_service.initialize_client():
        raise Exception("Failed to initialize Apify Service")

    # 3. Initialize XScraper
    x_scraper = XScraper(apify_service)

    # 4. Example Usage: Search by keyword
    keyword_tweets = await x_scraper.search_tweets_by_keyword(f"{' '.join(keywords)}", start=start, end=end, max_results=max_results)
    
    if len(keyword_tweets) == 0:
        return []
    
    pprint(keyword_tweets)
    posts_list = []
    for tweet in keyword_tweets:
        content = tweet.get('fullText')
        if not content:
            continue
        timestamp = tweet.get('createdAt')
        if timestamp:
            dt = datetime.strptime(timestamp, '%a %b %d %H:%M:%S +0000 %Y').strftime('%Y-%m-%d')
        else: 
            dt = 'null'
        posts_list.append({
            "url": tweet.get('url', 'www.x.com'),
            "date": dt,
            "content": content
        })
    
    analyzed_posts = gpt_infer(user_prompt=analyze_posts_prompt.replace('{keywords}', str(keywords)).replace('{posts_list}', str(posts_list)), system_prompt='你是一个专业的翻译和总结专家，能够对社媒帖子内容进行准确的总结和翻译。')

    return analyzed_posts


async def main():
    # task = x_prompt.replace("{topic}", "中国AI有什么新闻").replace(
    # "{date}", datetime.now().strftime("%Y-%m-%d")
    # )

    # result = x_agent.run(task)
    result = await get_x_posts('中国AI')

    print(result)




if __name__ == "__main__":
    asyncio.run(main())