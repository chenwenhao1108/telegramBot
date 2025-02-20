from datetime import datetime
from typing import List, Dict, Optional
from openai import OpenAI
from config.settings import settings
from smolagents import CodeAgent, OpenAIServerModel, tool
import re
import json

logger = settings.get_logger(__name__)

class OpenAIService:
    """Service class for OpenAI API interactions."""
    def __init__(self):
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url
        )
        self.model = OpenAIServerModel(
            model_id=settings.model_id,
            api_base=settings.openai_base_url,
            api_key=settings.openai_api_key
        )

    def infer(self, user_prompt: str, system_prompt: str = None, model: str = None, temperature: float = 0.6) -> str:
        """Make an inference using OpenAI API."""
        retries = 3
        for attempt in range(retries):
            try:
                completion = self.client.chat.completions.create(
                    model=model or settings.model_id,
                    messages=[
                        {"role": "system", "content": system_prompt} if system_prompt else None,
                        {"role": "user", "content": user_prompt}
                    ],
                    timeout=300,
                    temperature=temperature
                )
                res_raw = completion.choices[0].message.content
                
                # Try to parse JSON if present
                pattern = re.compile(r'```json\s*([\s\S]*?)\s*```')
                matches = pattern.findall(res_raw)
                if matches:
                    try:
                        return json.loads(matches[0], strict=False)
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON Decode Error: {e}")
                        return res_raw
                return res_raw
                
            except Exception as e:
                logger.error(f"OpenAI API call failed (attempt {attempt + 1}/{retries}): {e}")
                if attempt == retries - 1:
                    raise


async def parse_query(query: str, date: str) -> List[Dict]:
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
    openai_service = OpenAIService()
    
    analysis_result = openai_service.infer(user_prompt=analyze_query_prompt, system_prompt='你是一个关键词提取大师')
    return analysis_result


def analyze_content(news_list: List[str], user_question: str, task_type: str = "新闻") -> str:
    """Analyze news or posts content and answer user questions."""
    prompt = f"""下面是一个{task_type}列表，请总结这个列表里的{task_type}内容，并回答用户提问。
    {task_type}列表：
    {news_list}

    用户提问：
    {user_question}"""
    
    openai_service = OpenAIService()
    
    return openai_service.infer(
        user_prompt=prompt,
        system_prompt="你是一个文本内容分析师，擅长对文本内容进行分析总结，并根据总结回答用户提问。"
    )
    

def summarize_tweets(tweets: list) -> list:
    logger.info("Summarizing and translating tweets...")
    
    # 语言代码到中文名称的映射
    language_map = {
        "ab": "阿布哈兹语",
        "aa": "阿法尔语",
        "af": "南非语",
        "ak": "阿肯语",
        "sq": "阿尔巴尼亚语",
        "am": "阿姆哈拉语",
        "ar": "阿拉伯语",
        "an": "阿拉贡语",
        "hy": "亚美尼亚语",
        "as": "阿萨姆语",
        "av": "阿瓦尔语",
        "ae": "阿维斯陀语",
        "ay": "艾马拉语",
        "az": "阿塞拜疆语",
        "bm": "班巴拉语",
        "ba": "巴什基尔语",
        "eu": "巴斯克语",
        "be": "白俄罗斯语",
        "bn": "孟加拉语",
        "bi": "比斯拉马语",
        "bs": "波斯尼亚语",
        "br": "布列塔尼语",
        "bg": "保加利亚语",
        "my": "缅甸语",
        "ca": "加泰罗尼亚语",
        "ch": "查莫罗语",
        "ce": "车臣语",
        "ny": "齐切瓦语",
        "zh": "中文",
        "cu": "教会斯拉夫语",
        "cv": "楚瓦什语",
        "kw": "康沃尔语",
        "co": "科西嘉语",
        "cr": "克里语",
        "hr": "克罗地亚语",
        "cs": "捷克语",
        "da": "丹麦语",
        "dv": "迪维希语",
        "nl": "荷兰语",
        "dz": "宗喀语",
        "en": "英语",
        "eo": "世界语",
        "et": "爱沙尼亚语",
        "ee": "埃维语",
        "fo": "法罗语",
        "fj": "斐济语",
        "fi": "芬兰语",
        "fr": "法语",
        "fy": "弗里斯兰语",
        "ff": "富拉语",
        "gd": "苏格兰盖尔语",
        "gl": "加利西亚语",
        "lg": "干达语",
        "ka": "格鲁吉亚语",
        "de": "德语",
        "el": "希腊语",
        "kl": "格陵兰语",
        "gn": "瓜拉尼语",
        "gu": "古吉拉特语",
        "ht": "海地克里奥尔语",
        "ha": "豪萨语",
        "he": "希伯来语",
        "hz": "赫雷罗语",
        "hi": "印地语",
        "ho": "希里莫图语",
        "hu": "匈牙利语",
        "is": "冰岛语",
        "io": "伊多语",
        "ig": "伊博语",
        "id": "印尼语",
        "ia": "国际语",
        "ie": "介词",
        "iu": "因纽特语",
        "ik": "伊努皮克语",
        "ga": "爱尔兰语",
        "it": "意大利语",
        "ja": "日语",
        "jv": "爪哇语",
        "kn": "卡纳达语",
        "kr": "卡努里语",
        "ks": "克什米尔语",
        "kk": "哈萨克语",
        "km": "高棉语",
        "ki": "基库尤语",
        "rw": "卢旺达语",
        "ky": "吉尔吉斯语",
        "kv": "科米语",
        "kg": "刚果语",
        "ko": "韩语",
        "kj": "宽亚玛语",
        "ku": "库尔德语",
        "lo": "老挝语",
        "la": "拉丁语",
        "lv": "拉脱维亚语",
        "li": "林堡语",
        "ln": "林加拉语",
        "lt": "立陶宛语",
        "lu": "隆达语",
        "lb": "卢森堡语",
        "mk": "马其顿语",
        "mg": "马尔加什语",
        "ms": "马来语",
        "ml": "马拉雅拉姆语",
        "mt": "马耳他语",
        "gv": "马恩岛语",
        "mi": "毛利语",
        "mr": "马拉地语",
        "mh": "马绍尔语",
        "mn": "蒙古语",
        "na": "纳瓦霍语",
        "nv": "纳瓦霍语",
        "nd": "北恩德贝莱语",
        "nr": "南恩德贝莱语",
        "ng": "恩敦加语",
        "ne": "尼泊尔语",
        "no": "挪威语",
        "nb": "书面挪威语",
        "nn": "新挪威语",
        "ii": "彝语",
        "oc": "奥克语",
        "oj": "奥杰布瓦语",
        "or": "奥里亚语",
        "om": "奥罗莫语",
        "os": "奥塞梯语",
        "pi": "巴利语",
        "ps": "普什图语",
        "fa": "波斯语",
        "pl": "波兰语",
        "pt": "葡萄牙语",
        "pa": "旁遮普语",
        "qu": "克丘亚语",
        "ro": "罗马尼亚语",
        "rm": "罗曼什语",
        "rn": "基伦迪语",
        "ru": "俄语",
        "se": "北萨米语",
        "sm": "萨摩亚语",
        "sg": "桑戈语",
        "sa": "梵语",
        "sc": "撒丁语",
        "sr": "塞尔维亚语",
        "sn": "修纳语",
        "sd": "信德语",
        "si": "僧伽罗语",
        "sk": "斯洛伐克语",
        "sl": "斯洛文尼亚语",
        "so": "索马里语",
        "st": "南梭托语",
        "es": "西班牙语",
        "su": "巽他语",
        "sw": "斯瓦希里语",
        "ss": "斯瓦蒂语",
        "sv": "瑞典语",
        "tl": "塔加洛语",
        "ty": "塔希提语",
        "tg": "塔吉克语",
        "ta": "泰米尔语",
        "tt": "鞑靼语",
        "te": "泰卢固语",
        "th": "泰语",
        "bo": "藏语",
        "ti": "提格雷语",
        "to": "汤加语",
        "ts": "聪加语",
        "tn": "茨瓦纳语",
        "tr": "土耳其语",
        "tk": "土库曼语",
        "tw": "特威语",
        "ug": "维吾尔语",
        "uk": "乌克兰语",
        "ur": "乌尔都语",
        "uz": "乌兹别克语",
        "ve": "文达语",
        "vi": "越南语",
        "vo": "沃拉普克语",
        "wa": "瓦隆语",
        "cy": "威尔士语",
        "wo": "沃洛夫语",
        "xh": "科萨语",
        "yi": "意第绪语",
        "yo": "约鲁巴语",
        "za": "壮语",
        "zu": "祖鲁语",
        "unknown": "未知语言"
    }
    
    concise_tweets = []
    for tweet in tweets:
        content = tweet.get('fullText')
        if not content:
            continue
        
        timestamp = tweet.get('createdAt')
        if timestamp:
            dt = datetime.strptime(timestamp, '%a %b %d %H:%M:%S +0000 %Y').strftime('%Y-%m-%d %H:%M:%S')
        else: 
            dt = 'null'
            
        raw_lang = tweet.get("lang", "unknown")
        
        concise_tweets.append({
            "url": tweet.get('url', 'www.x.com'),
            "date": dt,
            "lang": language_map.get(raw_lang, "未知语言"),
            "content": content
        })
    
    if len(concise_tweets) == 0:
        logger.info(f"No tweets left after simplification")
        logger.info(f"Raw tweets: {tweets}")
        return
    
    prompt = f"""
你是一个专业的翻译和总结专家，能够对社媒帖子内容进行准确的总结和翻译，下面我将会给你一个列表的推特帖子，每个列表元素的结构为：{{"url": "https://www.x.com/post/1", "date": "2025-2-13", "content": "This is the content of the post."}}

**请你按照以下步骤进行分析：**
1. 分析每个帖子的content字段内容
2. 对每个帖子内容进行总结和翻译
4. 返回一个类似于下面结构的列表，**每个列表元素都是和下面示例中一样结构的字符串**

Example output:

```json
["# 习近平访问美国\n- 日期：2025-01-31 01:59:47\n- 语言：英语\n- 链接：https://www.bbc.com/news/world-us-canada-1234567890\n- 内容：习近平访问美国，与拜登总统会谈，讨论中美关系和全球问题。",
"# 习近平访问美国\n- 日期：2025-01-31 01:59:47\n- 语言: 英语\n- 链接：https://www.bbc.com/news/world-us-canada-1234567890\n- 内容：习近平访问美国，与拜登总统会谈，讨论中美关系和全球问题。"]
```

**请确保你的输出符合这个格式，且为中文， 并且不要添加任何多余内容和注释**

帖子列表：
{concise_tweets}
"""

    openai_service = OpenAIService()
    
    return openai_service.infer(
        user_prompt=prompt,
        system_prompt="你是一个专业的翻译和总结专家，能够对社媒帖子内容进行准确的总结和翻译。"
    )
    

def read_tweets_ids():
    with open("tweets_ids.txt", "r") as f:
        ids = json.load(f)
        return ids


def write_tweets_ids(ids):
    with open("tweets_ids.txt", "w") as f:
        json.dump(ids, f)
        return