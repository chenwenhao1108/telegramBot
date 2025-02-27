import asyncio
from datetime import datetime
from pprint import pprint
from typing import Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext, ContextTypes
import telegram
from config.settings import settings
from services.news_service import NewsService
from services.x_service import ApifyConfig, ApifyService, XScraper
from utils.utils import parse_query, analyze_content, read_tweets_ids, summarize_tweets, write_tweets_ids

logger = settings.get_logger(__name__)

class TelegramBotService:
    """Service class for Telegram bot operations."""
    def __init__(self, token: str):
        self.news_service = NewsService()
        self.start_message = """
您好！我是一个新闻搜索 Bot！
您可以输入以下指令进行使用：

输入 /news [查询句] 来查询新闻，例如：/news 最近的体育新闻
输入 /twitter_search [查询句] 来查询推特，例如：/twitter 最近的中国AI新闻
输入 /twitter_user [user id] 来查询推特用户，例如：/twitter_user elonmusk （请注意user id不是user name）
输入 /hourly [news/twitter] [特朗普/elonmusk]来设置定时推送新闻或twitter用户推文，例如：“/hourly news 特朗普” 或“/hourly /twitter elonmusk”
输入 /stop [news/twitter] 来停止定时推送
"""
        self.token = token

    async def initialize_x_service(self) -> Optional[XScraper]:
        """Initialize X (Twitter) scraping service."""
        try:
            apify_config = ApifyConfig()
            apify_service = ApifyService(apify_config)
            if not await apify_service.initialize_client():
                logger.error("Failed to initialize Apify service")
                return None
            return XScraper(apify_service)
        except Exception as e:
            logger.error(f"Error initializing X service: {e}")
            return None

    async def start(self, update: Update, context: CallbackContext) -> None:
        """Handle /start command."""
        await update.message.reply_text(self.start_message)

    async def twitter_search_command(self, update: Update, context: CallbackContext) -> None:
        """Handle /twitter command."""
        if not context.args:
            await update.message.reply_text('请在 /twitter_search 命令后输入您的问题，例如：/twitter_search 最近的体育新闻')
            return

        query = ' '.join(context.args)
        logger.info(f'User querying Twitter: {query}')
        await update.message.reply_text(f'正在查询：{query}，请稍等...')

        x_scraper = await self.initialize_x_service()
        if not x_scraper:
            await update.message.reply_text("Twitter服务初始化失败，请稍后重试")
            return

        max_retries = 3
        for retry in range(max_retries):
            try:
                parsed_result = await parse_query(query = query, date = datetime.now().strftime("%Y-%m-%d"))
                
                logger.info(f'Parsed user query: {parsed_result}')
                
                keywords = parsed_result.get("keywords")
                if not keywords:
                    await update.message.reply_text(f"解析keywords失败，正在重试 {retry + 1}/{max_retries}")
                    continue
                
                start = parsed_result.get('startDate', None)
                end = parsed_result.get('endDate', None)
                
                raw_tweets = await x_scraper.search_tweets_by_keyword(
                    f"{' '.join(keywords)}", start=start, end=end
                )
                
                if not raw_tweets:
                    if retry == max_retries - 1:
                        await update.message.reply_text("未找到相关推文，请尝试换个话题或拉长时间间隔")
                    continue
                
                tweets = summarize_tweets(raw_tweets)
                
                for tweet in tweets:
                    try:
                        await update.message.reply_text(text=tweet)
                        await asyncio.sleep(0.5)
                    except telegram.error.RetryAfter as e:
                        await asyncio.sleep(e.retry_after)
                        await update.message.reply_text(text=tweet)

                # Analyze tweets
                try:
                    formatted_tweets = "\n\n".join(tweets)
                    analysis = analyze_content(
                        formatted_tweets,
                        query,
                        task_type="推特帖子"
                    )
                    await update.message.reply_text(text=analysis)
                except Exception as e:
                    logger.error(f"Failed to analyze tweets: {e}")
                    await update.message.reply_text("推文分析失败，但已为您展示所有推文")
                break

            except Exception as e:
                logger.error(f"Error in twitter command (attempt {retry + 1}/{max_retries}): {e}")
                if retry == max_retries - 1:
                    await update.message.reply_text("获取推文时出错，请稍后重试")


    async def twitter_user_command(self, update: Update, context: CallbackContext) -> None:
        if not context.args or len(context.args) < 1:
            await update.message.reply_text('请在 /twitter_user 命令后输入用户id（而非用户名）+空格+月数，例如：/twitter_user elonmusk 3 来查询马斯克最近三个月的帖子')
            return
        
        user_id = context.args[0]
        
        try: 
            months_back = int(context.args[1]) if len(context.args) > 1 else 3
        except ValueError:
            await update.message.reply_text('请输入阿拉伯数字作为月数，例如：/twitter_user elonmusk 3')
            return
        
        await update.message.reply_text(f'正在查询：{user_id} 最近{months_back}个月的推文，请稍等...')
        
        
        x_scraper = await self.initialize_x_service()
        
        if not x_scraper:
            await update.message.reply_text("Twitter服务初始化失败，请稍后重试")
            return
        
        raw_tweets = await x_scraper.get_profile_tweets(user_id, months_back)
            
        if not raw_tweets:
            await update.message.reply_text("未找到相关推文，请检查用户id是否正确")
            return
        
        tweets = summarize_tweets(raw_tweets)
        
        for tweet in tweets:
            try:
                await update.message.reply_text(text=tweet)
                await asyncio.sleep(0.5)
            except telegram.error.RetryAfter as e:
                await asyncio.sleep(e.retry_after)
                await update.message.reply_text(text=tweet)
        

    async def news_command(self, update: Update, context: CallbackContext) -> None:
        """Handle /news command."""
        if not context.args:
            await update.message.reply_text('请在 /news 命令后输入您的问题，例如：/news 最近的体育新闻')
            return

        query = ' '.join(context.args)
        logger.info(f'User querying news: {query}')
        await update.message.reply_text(f'正在查询：{query}，请稍等...')

        max_retries = 3
        for retry in range(max_retries):
            try:
                news_items = self.news_service.get_news(
                    query,
                    date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )

                if not news_items:
                    if retry == max_retries - 1:
                        await update.message.reply_text("未找到相关新闻，请尝试换个话题或拉长时间间隔")
                        return
                    continue
                
                if isinstance(news_items, str):
                    await update.message.reply_text(news_items)
                    return

                await update.message.reply_text(f'获取到了{len(news_items)}条新闻')
                
                for article in news_items:
                    try:
                        await update.message.reply_text(text=article)
                        await asyncio.sleep(0.5)
                    except telegram.error.RetryAfter as e:
                        await asyncio.sleep(e.retry_after)
                        await update.message.reply_text(text=article)

                # Analyze news
                try:
                    formatted_news = "\n\n".join(news_items)
                    analysis = analyze_content(
                        formatted_news,
                        query,
                        task_type="新闻报道"
                    )
                    await update.message.reply_text(text=analysis)
                except Exception as e:
                    logger.error(f"Failed to analyze news: {e}")
                    await update.message.reply_text("新闻分析失败，但已为您展示所有新闻")
                break

            except Exception as e:
                logger.error(f"Error in news command (attempt {retry + 1}/{max_retries}): {e}")
                if retry == max_retries - 1:
                    await update.message.reply_text("获取新闻时出错，请稍后重试")
    
    @staticmethod
    async def send_scheduled_news(context: ContextTypes.DEFAULT_TYPE) -> None:
        """Callback for scheduled news updates."""
        job_data = context.job.data
        query = f"{job_data['message']} **in recent 1 hour**"
        news_service = job_data['news_service']
        
        logger.info(f"Sending scheduled news update for query: {query}")
        
        try:
            news_items = news_service.get_news(
                query,
                date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )

            if not news_items:
                await context.bot.send_message(
                    chat_id=job_data['chat_id'],
                    text=f"最近一小时并无关于{job_data['message']}的新闻"
                )
                return

            if isinstance(news_items, str):
                await context.bot.send_message(
                    chat_id=job_data['chat_id'],
                    text=news_items
                )
                return
            
            await context.bot.send_message(
                chat_id=job_data['chat_id'],
                text=f'Hourly news about: {job_data["message"]}'
            )

            for article in news_items:
                try:
                    await context.bot.send_message(
                        chat_id=job_data['chat_id'],
                        text=article
                    )
                    await asyncio.sleep(0.5)
                except telegram.error.RetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                    await context.bot.send_message(
                        chat_id=job_data['chat_id'],
                        text=article
                    )

        except Exception as e:
            logger.error(f"Error in scheduled news: {e}")
            await context.bot.send_message(
                chat_id=job_data['chat_id'],
                text="获取定时新闻时出错，请稍后重试"
            )

    @staticmethod
    async def send_scheduled_tweets(context: ContextTypes.DEFAULT_TYPE) -> None:
        """Callback for scheduled tweets updates."""
        job_data = context.job.data
        user_id = job_data['user_id']
        chat_id = job_data['chat_id']
        x_scraper = job_data['x_scraper']
        
        logger.info(f"Sending scheduled tweets update for user id: {user_id}")
    
        
        raw_tweets = await x_scraper.get_profile_tweets(user_id, 1)
                    
        if not raw_tweets:
            await context.bot.send_message(
                        chat_id=chat_id,
                        text="未找到相关推文，请检查用户id是否正确"
                    )
            return
        
        old_ids = read_tweets_ids()
        new_ids = [tweet['id'] for tweet in raw_tweets]

        if set(new_ids) - set(old_ids):
            write_tweets_ids(new_ids)
            
            tweets = summarize_tweets(raw_tweets)
            
            for tweet in tweets:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=tweet
                    )
                    await asyncio.sleep(0.5)
                except telegram.error.RetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=tweet
                    )
        else:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"没有新的推文, 时间：{now}"
                    )
                
        
    async def hourly(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /hourly command."""
        if not context.job_queue:
            await update.message.reply_text("定时任务系统未就绪，请稍后重试")
            return
            
        chat_id = update.effective_chat.id
        
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("⚠️ 请提供要监听的类型和twitter id或新闻关键词，例如：/hourly news 特朗普 或 /hourly twitter elonmusk")
            return
        
        schedule_type = context.args[0]
        query = context.args[1]
        
        # 初始化jobs字典（如果不存在）
        if 'jobs' not in context.chat_data:
            context.chat_data['jobs'] = {}
        
        # 如果该类型的任务已存在，先移除
        if schedule_type in context.chat_data['jobs']:
            context.chat_data['jobs'][schedule_type].schedule_removal()
        
        if schedule_type == 'news':
            news_service = self.news_service
            
            new_job = context.job_queue.run_repeating(
                callback=self.send_scheduled_news,
                interval=3600,
                first=1,
                data={'message': query, 'chat_id': chat_id, 'news_service': news_service},
                chat_id=chat_id
            )
            context.chat_data['jobs'][schedule_type] = new_job
            await update.message.reply_text(f"✅ 开始每小时推送关于：{query} 的新闻")
            
        elif schedule_type == 'twitter':
            x_scraper = await self.initialize_x_service()
        
            if not x_scraper:
                await context.bot.send_message(
                            chat_id=chat_id,
                            text="Twitter服务初始化失败，请稍后重试"
                        )
                return
            
            new_job = context.job_queue.run_repeating(
                callback=self.send_scheduled_tweets,
                interval=3600,
                first=1,
                data={'user_id': query, 'chat_id': chat_id, 'x_scraper': x_scraper,},
                chat_id=chat_id
            )

            context.chat_data['jobs'][schedule_type] = new_job
            await update.message.reply_text(f"✅ 开始每小时推送 {query} 的推文")
        
        else:
            await update.message.reply_text("❌ 不支持的类型，目前支持 news 和 twitter")

    async def stop_hourly(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /stop command."""
        if not context.args:
            await update.message.reply_text("⚠️ 请指定要停止的类型，例如：/stop news 或 /stop twitter")
            return
            
        schedule_type = context.args[0]
        
        if 'jobs' in context.chat_data and schedule_type in context.chat_data['jobs']:
            context.chat_data['jobs'][schedule_type].schedule_removal()
            del context.chat_data['jobs'][schedule_type]
            await update.message.reply_text(f"✅ 已停止 {schedule_type} 的定时推送")
        else:
            await update.message.reply_text(f"❌ 没有正在运行的 {schedule_type} 定时任务")

    def run(self):
        """Start the Telegram bot."""
        try:
            # 创建应用实例
            application = Application.builder().token(self.token).concurrent_updates(True).build()

            # Add command handlers
            application.add_handler(CommandHandler("start", self.start))
            application.add_handler(CommandHandler("news", self.news_command))
            application.add_handler(CommandHandler("twitter_search", self.twitter_search_command))
            application.add_handler(CommandHandler("twitter_user", self.twitter_user_command))
            application.add_handler(CommandHandler("hourly", self.hourly))
            application.add_handler(CommandHandler("stop", self.stop_hourly))

            logger.info("Starting Telegram bot...")
            application.run_polling()

        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}")
            raise
        