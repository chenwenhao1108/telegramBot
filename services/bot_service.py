import asyncio
from datetime import datetime, timedelta
from pprint import pprint
from typing import Optional
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackContext, ContextTypes, TypeHandler
import telegram
from config.settings import settings
from services.news_service import NewsService
from services.x_service import ApifyConfig, ApifyService, XScraper
from utils.utils import parse_query, analyze_content, read_tweets_ids, summarize_tweets, write_tweets_ids, analyze_message, analyze_scheduled_messages
from telethon.tl.types import User, Chat, Channel

import os
import json
import time
import re

# 导入Telethon相关库
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon import functions

logger = settings.get_logger(__name__)

class TelegramBotService:
    """Service class for Telegram bot operations."""
    def __init__(self, token: str, bot_type: str, start_message: str):
        self.news_service = NewsService()
        self.start_message = start_message
        self.bot_type = bot_type
        self.token = token
        # Telethon客户端
        self.telethon_client = None
        # 存储应用实例
        self.application = None
        # 转发配置文件路径
        self.config_file = "./forward_configs.json"
        # 转发配置列表
        self.forward_configs = self.load_forward_configs()
        # 消息处理器字典，用于管理和移除
        self.message_handlers = {}
        # 存储半小时内的群组消息用于定时分析
        self.group_messages = {}
        # 存储定时任务引用用于在stop_forward中移除任务
        self.scheduled_jobs = {}
        
    def load_forward_configs(self) -> list:
        """从JSON文件加载转发配置"""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"加载转发配置文件失败: {e}")
        return []

    def save_forward_configs(self):
        """保存转发配置到JSON文件"""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.forward_configs, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"保存转发配置文件失败: {e}")

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

    async def initialize_telethon_client(self):
        """初始化Telethon客户端"""
        try:
            # 从settings获取API凭据和会话字符串
            api_id = settings.telegram_api_id
            api_hash = settings.telegram_api_hash
            session_string = settings.telegram_session_string
            
            # 如果已有客户端在运行并已连接，直接返回
            if self.telethon_client and self.telethon_client.is_connected():
                return self.telethon_client
                
            # 创建新的Telethon客户端
            self.telethon_client = TelegramClient(
                StringSession(session_string),
                api_id,
                api_hash
            )
            
            # 连接到Telegram
            await self.telethon_client.connect()
            
            # 检查是否已授权
            if not await self.telethon_client.is_user_authorized():
                logger.error("Telethon客户端未授权")
                await self.telethon_client.disconnect()
                self.telethon_client = None
                return None
                
            return self.telethon_client
        except Exception as e:
            logger.error(f"初始化Telethon客户端时出错: {e}")
            if self.telethon_client:
                await self.telethon_client.disconnect()
                self.telethon_client = None
            return None

    # 重启bot后自动从forward_configs中恢复监听列表
    async def restore_message_handlers(self):
        """恢复所有已保存的转发配置的消息处理器"""
        try:
            # 初始化Telethon客户端
            if not self.telethon_client or not self.telethon_client.is_connected():
                client = await self.initialize_telethon_client()
                if not client:
                    logger.error('恢复消息处理器失败：Telethon客户端初始化失败')
                    return
                self.telethon_client = client
            
            # 清空旧处理器
            await self.telethon_client.disconnect()
            await self.telethon_client.connect()
            
            restored_count = 0
            for config in self.forward_configs:
                try:
                    source_chat = config['source_chat']
                    # 添加实体验证
                    try:
                        entity = await self.telethon_client.get_entity(source_chat)
                        logger.info(f"群组实体验证成功: ID={entity.id} Title={entity.title}")
                    except Exception as e1:
                        logger.error(f"群组实体验证失败: {source_chat} 错误: {e1}，尝试其他方法...")
                        # 如果是数字ID，尝试不同的格式
                        if isinstance(source_chat, int) or (isinstance(source_chat, str) and source_chat.lstrip('-').isdigit()):
                            source_id = int(source_chat)
                            
                            # 尝试不同的ID格式
                            possible_ids = [
                                source_id,  # 原始ID
                                -source_id if source_id > 0 else abs(source_id),  # 正负转换
                                int(f"-100{abs(source_id)}") if not str(source_id).startswith('-100') else source_id,  # 添加-100前缀
                                int(str(source_id).replace('-100', '')) if str(source_id).startswith('-100') else source_id  # 移除-100前缀
                            ]
                            
                            for possible_id in possible_ids:
                                try:
                                    entity = await self.telethon_client.get_entity(possible_id)
                                    # 如果成功，更新配置中的ID
                                    if entity:
                                        logger.info(f"使用替代ID {possible_id} 成功获取实体")
                                        config['source_chat'] = possible_id
                                        source_chat = possible_id
                                        break
                                except Exception:
                                    continue
                            else:
                                # 所有尝试都失败
                                logger.error(f"无法使用任何ID格式获取实体: {source_chat}")
                                continue
                    target_chat = config['target_chat']
                    group_name = config['group_name']
                    config_id = config['id']
                    
                    # 创建新处理器前断开旧连接
                    if self.message_handlers.get(config['id']):
                        self.message_handlers[config['id']].disconnect()
                    
                    # 使用通用方法创建消息处理器
                    forward_handler = self.create_forward_handler(
                        client=self.telethon_client,
                        source_chat=source_chat,
                        target_chat=target_chat,
                        group_name=group_name,
                        bot=self.application.bot
                    )
                    
                    # 保存处理器引用
                    self.message_handlers[config_id] = forward_handler
                    restored_count += 1
                    
                except Exception as e:
                    logger.error(f"恢复消息处理器失败 (配置ID: {config.get('id', 'unknown')}): {e}")
                finally:
                    asyncio.sleep(0.5)  # 短暂延迟以避免过度请求
            
            logger.info(f"成功恢复 {restored_count}/{len(self.forward_configs)} 个消息处理器")
            # 添加连接状态检查（调试用）
            logger.info(f"当前客户端连接状态: {self.telethon_client.is_connected()}")
            logger.info(f"活跃事件处理器数量: {len(self.telethon_client.list_event_handlers())}")
            
        except Exception as e:
            logger.error(f"恢复消息处理器过程中出错: {e}")

    # 创建消息转发处理器以便在forward_new和restore_message_handlers中复用
    def create_forward_handler(self, client, source_chat, target_chat, group_name, bot=None):
        """创建消息转发处理器函数"""
        @client.on(events.NewMessage(chats=source_chat))
        async def forward_handler(event):
            """处理新消息并转发"""
            try:
                # 获取消息内容
                message = event.message
                
                # 记录所有收到的消息，包括消息类型
                msg_type = "未知类型"
                if message.text:
                    msg_type = "文本消息"
                elif message.media:
                    msg_type = "媒体消息"
                elif message.sticker:
                    msg_type = "贴纸"
                elif message.document:
                    msg_type = "文档"
                elif message.voice:
                    msg_type = "语音消息"
                elif message.video:
                    msg_type = "视频"
                elif message.video_note:
                    msg_type = "视频笔记"
                elif message.gif:
                    msg_type = "GIF"

                # 先记录原始消息，确保我们看到了所有消息
                logger.info(f"消息ID: {message.id} 消息来源：{source_chat} ({group_name}) 消息类型：{msg_type} 消息内容: {message.text[:100] if message.text else '非文本消息'}{'...' if (message.text and len(message.text) > 100) else ''}")
                
                # 创建唯一标识符
                config_id = f"{source_chat}_{target_chat}"
                
                if message.text:
                    
                    if not self.group_messages.get(config_id):
                        self.group_messages[config_id] = {}
                        self.group_messages[config_id]['messages'] = []
                        self.group_messages[config_id]['group_name'] = group_name
                    # 每次来新消息都储存到group_messages用于定时分析
                    self.group_messages[config_id]['messages'].append(message.text)
                    
                    # 使用异步但不等待的方式进行消息分析
                    asyncio.create_task(self._process_message(message, source_chat, target_chat, group_name, bot))
        
            except Exception as e:
                logger.error(f"Error forwarding message via Telethon: {e}")
                
        return forward_handler
    
    async def _process_message(self, message, source_chat, target_chat, group_name, bot=None):
        """分离消息处理逻辑，避免阻塞主事件处理器"""
        try:
            if message.text:
                analysis = await analyze_message(message=message.text)
                logger.info(f"消息ID: {message.id}，分析结果: {analysis}")
                
                if not isinstance(analysis, dict) or not analysis.get('is_illegal_comment', False):
                    return
                
                # 获取发送者信息
                sender_info = "未知用户"
                if message.sender:
                    sender_id = message.sender.id
                    if message.sender.username:
                        sender_info = f"@{message.sender.username} (<a href=\"https://t.me/{message.sender.username}\">用户链接</a>)"
                    elif message.sender.first_name:
                        sender_name = message.sender.first_name
                        if message.sender.last_name:
                            sender_name += f" {message.sender.last_name}"
                        sender_info = f"{sender_name} (<a href=\"tg://user?id={sender_id}\">用户链接</a>)"

                text = f"""⚠️ 来自 \"{group_name}\" 的非法消息:
                \n发送者：\n{sender_info}
                \n发送时间：\n{(message.date + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')} (北京时间)
                \n原因：\n{analysis.get('reason', '该消息表达了非法内容')}
                \n原文：\n{message.text}"""
                
                # 使用提供的bot或context.bot发送消息
                message_bot = bot if bot else self.application.bot
                current_chat_id = target_chat
                try:
                    await message_bot.send_message(
                        chat_id=current_chat_id,
                        text=text,
                        parse_mode=ParseMode.HTML
                    )
                except telegram.error.BadRequest as e:
                    # 检查是否是群组迁移错误
                    if "Group migrated to supergroup" in str(e):
                        # 提取新的超级群组ID
                        new_id_match = re.search(r"New chat id: (-\d+)", str(e))
                        if new_id_match:
                            current_chat_id = new_id_match.group(1)
                            logger.info(f"群组已迁移到超级群组。旧ID: {target_chat}, 新ID: {current_chat_id}")
                            
                            # 更新配置中的目标群组ID
                            self._update_migrated_chat_id(target_chat, current_chat_id)
                            
                            # 使用新ID重试发送消息
                            await message_bot.send_message(
                                chat_id=current_chat_id,
                                text=text,
                                parse_mode=ParseMode.HTML
                            )
                        else:
                            logger.error(f"无法从错误消息中提取新的群组ID: {e}")
                    else:
                        # 其他BadRequest错误
                        logger.error(f"发送消息时出错: {e}")
                except Exception as e:
                    logger.error(f"发送消息时出错: {e}")
            
                # 如果有媒体内容，也可以处理
                if message.media:
                    # 下载媒体文件
                    file_path = await message.download_media("./temp/")
                    if file_path:
                        try:
                            # 根据媒体类型发送，也可以添加其他类型
                            if message.photo:
                                with open(file_path, 'rb') as photo:
                                    await message_bot.send_photo(
                                        chat_id=current_chat_id,
                                        photo=photo,
                                        caption=f"📷 来自 \"{group_name}\" 的图片 | {message.text if message.text else ''}"
                                    )
                        except Exception as e:
                            logger.error(f"Error sending media: {e}")
                        finally:
                            # 确保在任何情况下都尝试删除临时文件
                            try:
                                if os.path.exists(file_path):
                                    os.remove(file_path)
                            except Exception as e:
                                logger.error(f"Error removing temporary file {file_path}: {e}")
        
                logger.info(f"Message forwarded from {source_chat} ({group_name}) to {target_chat}")
    
        except Exception as e:
            logger.error(f"Error processing message in _process_message: {e}")
            
    def _update_migrated_chat_id(self, old_chat_id, new_chat_id):
        """更新已迁移群组的ID"""
        try:
            # 更新内存中的转发配置
            updated = False
            for config in self.forward_configs:
                # 检查源群组和目标群组
                if str(config['source_chat']) == str(old_chat_id):
                    config['source_chat'] = new_chat_id
                    logger.info(f"已更新源群组ID: {old_chat_id} -> {new_chat_id}")
                    updated = True
                
                if str(config['target_chat']) == str(old_chat_id):
                    config['target_chat'] = new_chat_id
                    logger.info(f"已更新目标群组ID: {old_chat_id} -> {new_chat_id}")
                    updated = True
                
                # 更新配置ID
                if updated:
                    old_id = config['id']
                    config['id'] = f"{config['source_chat']}_{config['target_chat']}"
                    logger.info(f"已更新配置ID: {old_id} -> {config['id']}")
                    
                    # 更新消息处理器字典中的键
                    if old_id in self.message_handlers:
                        self.message_handlers[config['id']] = self.message_handlers.pop(old_id)
            
            # 如果有更新，保存到文件
            if updated:
                self.save_forward_configs()
                logger.info("已保存更新后的转发配置")
                
                # 重新初始化消息处理器
                asyncio.create_task(self.restore_message_handlers())
                
        except Exception as e:
            logger.error(f"更新迁移群组ID时出错: {e}")

    async def forward_new(self, update: Update, context: CallbackContext) -> None:
        """设置转发新消息"""
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                '请提供源群组ID/用户名或邀请链接：\n'
                '/forward_new [源群组ID/用户名/邀请链接]\n\n'
                '例如：\n'
                '/forward_new @groupname\n'
                '/forward_new -1001234567890\n'
                '/forward_new https://t.me/joinchat/abcdef...'
            )
            return
            
        try:
            # 初始化Telethon客户端
            client = await self.initialize_telethon_client()
            if not client:
                await update.message.reply_text('❌ Telethon客户端初始化失败，请检查API凭据和会话字符串')
                logger.error('Telethon客户端初始化失败，请检查API凭据和会话字符串')
                return
                
            # 获取源群组或邀请链接
            source_input = context.args[0]
            
            # 获取目标群组ID（当前聊天ID）
            target_chat = update.effective_chat.id
            
            # 处理邀请链接
            source_chat = source_input
            group_name = source_input
            if 't.me/' in source_input or 'telegram.me/' in source_input:
                await update.message.reply_text('🔄 检测到邀请链接，正在尝试加入群组...')
                try:
                    # 提取邀请链接的hash部分
                    invite_hash = None
                    if '/joinchat/' in source_input:
                        # 私有群组链接格式: t.me/joinchat/HASH
                        invite_hash = source_input.split('/joinchat/')[-1].split('?')[0]
                    elif '/+' in source_input:
                        # 新的私有群组链接格式: t.me/+HASH
                        invite_hash = source_input.split('/+')[-1].split('?')[0]
                    else:
                        # 公开群组链接格式: t.me/username
                        username = source_input.split('t.me/')[-1].split('?')[0]
                        try:
                            entity = await client.get_entity(username)
                            source_chat = entity.id
                            if isinstance(entity, Channel):
                                # 超级群组/频道ID需要加上-100前缀
                                source_chat = -1000000000000 - entity.id
                                logger.info(f"将频道ID {entity.id} 转换为客户端格式: {source_chat}")
                            elif isinstance(entity, Chat):
                                # 普通群组ID需要加上负号
                                source_chat = -entity.id
                                logger.info(f"将群组ID {entity.id} 转换为客户端格式: {source_chat}")
                            else:
                                # 用户或其他类型实体保持原样
                                source_chat = entity.id
                                logger.info(f"使用原始实体ID: {source_chat}")
                            group_name = getattr(entity, 'title', str(source_chat))
                            
                            # 尝试加入公开群组
                            try:
                                await client(functions.channels.JoinChannelRequest(channel=entity))
                                await update.message.reply_text(f'✅ 成功加入群组 "{group_name}"')
                            except Exception as join_err:
                                if "ALREADY_PARTICIPANT" in str(join_err):
                                    await update.message.reply_text(f'ℹ️ 您已经是群组 "{group_name}" 的成员')
                                else:
                                    logger.warning(f"加入公开群组时出现错误: {join_err}")
                                    await update.message.reply_text(f'⚠️ 加入群组时出现问题: {str(join_err)}')
                            
                            await update.message.reply_text(f'✅ 成功获取群组 "{group_name}" 信息，ID: {source_chat}')
                            # 跳过后续的加入群组步骤（这里指的是私有群组的加入流程）
                            invite_hash = None
                        except Exception as e:
                            await update.message.reply_text(f'❌ 无法获取群组信息: {str(e)}')
                            logger.error(f'获取群组信息失败: {str(e)}')
                            return
                    
                    # 如果是私有群组链接，尝试加入
                    if invite_hash:
                        logger.info(f"尝试使用hash加入群组: {invite_hash}")
                        try:
                            result = await client(functions.messages.ImportChatInviteRequest(
                                hash=invite_hash
                            ))
                            # 获取加入的群组ID
                            if hasattr(result, 'chats') and result.chats:
                                source_chat = -1001000000000 - result.chats[0].id  # 转换为超级群组格式
                                group_name = result.chats[0].title
                                await update.message.reply_text(f'✅ 成功加入群组 "{group_name}"，ID: {source_chat}')
                            else:
                                await update.message.reply_text('❌ 加入群组成功但无法获取群组ID')
                                logger.error(f"加入群组成功但无法获取群组ID: {result}")
                                return
                        except Exception as e:
                            # 可能已经在群组中
                            if "ALREADY_PARTICIPANT" in str(e):
                                await update.message.reply_text('ℹ️ 您已经是该群组的成员')
                                # 尝试获取群组信息
                                try:
                                    # 尝试从对话列表中查找该群组
                                    dialogs = await client.get_dialogs()
                                    for dialog in dialogs:
                                        if invite_hash in str(dialog.entity):
                                            source_chat = dialog.entity.id
                                            group_name = dialog.entity.title
                                            await update.message.reply_text(f'✅ 找到群组 "{group_name}"，ID: {source_chat}')
                                            break
                                except Exception as inner_e:
                                    await update.message.reply_text('⚠️ 无法获取群组信息，请使用群组ID或用户名设置转发')
                                    logger.error(f"无法获取群组信息: {str(inner_e)}")
                                    return
                            elif "INVITE_HASH_EXPIRED" in str(e) or "not valid anymore" in str(e):
                                await update.message.reply_text('❌ 邀请链接已过期，请获取新的邀请链接')
                                logger.error(f'邀请链接已过期: {str(e)}')
                                return
                            else:
                                await update.message.reply_text(f'❌ 无法加入群组: {str(e)}')
                                logger.error(f'加入群组失败: {str(e)}')
                                return
                except Exception as e:
                    await update.message.reply_text(f'❌ 处理邀请链接时出错: {str(e)}')
                    logger.error(f'处理邀请链接时出错: {str(e)}')
                    return
            else:
                # 尝试获取群组信息
                try:
                    entity = await client.get_entity(source_chat)
                    group_name = getattr(entity, 'title', str(source_chat))
                    
                    # 尝试加入群组（如果是公开群组）
                    if hasattr(entity, 'username') and entity.username:
                        try:
                            await client(functions.channels.JoinChannelRequest(channel=entity))
                            await update.message.reply_text(f'✅ 成功加入群组 "{group_name}"')
                        except Exception as join_err:
                            if "ALREADY_PARTICIPANT" in str(join_err):
                                await update.message.reply_text(f'ℹ️ 您已经是群组 "{group_name}" 的成员')
                            else:
                                logger.warning(f"加入公开群组时出现错误: {join_err}")
                                await update.message.reply_text(f'⚠️ 加入群组时出现问题: {str(join_err)}')
                except Exception as e:
                    await update.message.reply_text(f'❌ 无法获取群组信息: {str(e)}')
                    return
            
            # 使用通用方法创建消息处理器
            forward_handler = self.create_forward_handler(
                client=client,
                source_chat=source_chat,
                target_chat=target_chat,
                group_name=group_name
            )
            
            # 检查是否已经在监听该群组
            is_listening = False
            for config in self.forward_configs:
                if config['source_chat'] == source_chat and config['target_chat'] == target_chat:
                    is_listening = True
                    break

            # 创建唯一标识符
            config_id = f"{source_chat}_{target_chat}"
            
            if not is_listening:
                # 保存转发配置
                config = {
                    'id': config_id,
                    'source_chat': source_chat,
                    'target_chat': target_chat,
                    'group_name': group_name
                }
                self.forward_configs.append(config)
                # 在成功设置转发后，保存配置
                self.save_forward_configs()
            self.message_handlers[config_id] = forward_handler

            if not target_chat in self.scheduled_jobs:
                # 创建定时任务
                new_job = context.job_queue.run_repeating(
                        callback=self.send_scheduled_message_analysis,
                        interval=1800, # 每半小时分析一次
                        first=1800,
                        data={'target_chat': target_chat, 'source_chat': source_chat, 'group_name': group_name, 'config_id': config_id},
                        chat_id=target_chat
                    )
                # 保存任务引用
                self.scheduled_jobs[target_chat] = new_job
            
            await update.message.reply_text(f'✅ 已设置转发 "{group_name}" 的新消息到当前群组')
            logger.info(f"Message forwarding set up from {source_chat} ({group_name}) to {target_chat}")
            
        except Exception as e:
            logger.error(f"Error setting up message forwarding: {e}")
            await update.message.reply_text(f'❌ 设置消息转发时出错: {str(e)}')

    async def get_history(self, update: Update, context: CallbackContext) -> None:
        """获取群组历史消息"""
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                '请提供源群组ID/用户名/邀请链接和查询句：\n'
                '/get_history [源群组ID/用户名/邀请链接] [查询句]\n\n'
                '例如：\n'
                '/get_history @groupname 这个群组内有哪些关于足球的消息\n'
                '/get_history https://t.me/joinchat/abcdef... 查询最近的讨论\n'
            )
            return
            
        try:
            # 初始化Telethon客户端
            client = await self.initialize_telethon_client()
            if not client:
                await update.message.reply_text('❌ Telethon客户端初始化失败，请检查API凭据和会话字符串')
                return
                
            # 获取源群组和用户查询句
            source_input = context.args[0]
            query = ' '.join(context.args[1:]) if len(context.args) > 1 else "所有消息"
            
            # 获取目标群组ID（当前聊天ID）
            target_chat = update.effective_chat.id
            
            # 处理邀请链接
            source_chat = source_input
            group_name = source_input
            if 't.me/' in source_input or 'telegram.me/' in source_input:
                await update.message.reply_text('🔄 检测到邀请链接，正在尝试加入群组...')
                try:
                    # 提取邀请链接的hash部分
                    invite_hash = None
                    if '/joinchat/' in source_input:
                        # 私有群组链接格式: t.me/joinchat/HASH
                        invite_hash = source_input.split('/joinchat/')[-1].split('?')[0]
                    elif '/+' in source_input:
                        # 新的私有群组链接格式: t.me/+HASH
                        invite_hash = source_input.split('/+')[-1].split('?')[0]
                    else:
                        # 公开群组链接格式: t.me/username
                        username = source_input.split('t.me/')[-1].split('?')[0]
                        try:
                            entity = await client.get_entity(username)
                            source_chat = entity.id
                            group_name = getattr(entity, 'title', str(source_chat))
                            
                            # 尝试加入公开群组
                            try:
                                await client(functions.channels.JoinChannelRequest(channel=entity))
                                await update.message.reply_text(f'✅ 成功加入群组 "{group_name}"')
                            except Exception as join_err:
                                if "ALREADY_PARTICIPANT" in str(join_err):
                                    await update.message.reply_text(f'ℹ️ 您已经是群组 "{group_name}" 的成员')
                                else:
                                    logger.warning(f"加入公开群组时出现错误: {join_err}")
                                    await update.message.reply_text(f'⚠️ 加入群组时出现问题: {str(join_err)}')
                            
                            await update.message.reply_text(f'✅ 成功获取群组 "{group_name}" 信息，ID: {source_chat}')
                            # 跳过后续的加入群组步骤（这里指的是私有群组的加入流程）
                            invite_hash = None
                        except Exception as e:
                            await update.message.reply_text(f'❌ 无法获取群组信息: {str(e)}')
                            logger.error(f'获取群组信息失败: {str(e)}')
                            return
                    
                    # 如果是私有群组链接，尝试加入
                    if invite_hash:
                        logger.info(f"尝试使用hash加入群组: {invite_hash}")
                        try:
                            result = await client(functions.messages.ImportChatInviteRequest(
                                hash=invite_hash
                            ))
                            # 获取加入的群组ID
                            if hasattr(result, 'chats') and result.chats:
                                source_chat = -1001000000000 - result.chats[0].id  # 转换为超级群组格式
                                group_name = result.chats[0].title
                                await update.message.reply_text(f'✅ 成功加入群组 "{group_name}"，ID: {source_chat}')
                            else:
                                await update.message.reply_text('❌ 加入群组成功但无法获取群组ID')
                                logger.error(f"加入群组成功但无法获取群组ID: {result}")
                                return
                        except Exception as e:
                            # 可能已经在群组中
                            if "ALREADY_PARTICIPANT" in str(e):
                                await update.message.reply_text('ℹ️ 您已经是该群组的成员')
                                # 尝试获取群组信息
                                try:
                                    # 尝试从对话列表中查找该群组
                                    dialogs = await client.get_dialogs()
                                    for dialog in dialogs:
                                        if invite_hash in str(dialog.entity):
                                            source_chat = dialog.entity.id
                                            group_name = dialog.entity.title
                                            await update.message.reply_text(f'✅ 找到群组 "{group_name}"，ID: {source_chat}')
                                            break
                                except Exception as inner_e:
                                    await update.message.reply_text('⚠️ 无法获取群组信息，请使用群组ID或用户名设置转发')
                                    logger.error(f"无法获取群组信息: {str(inner_e)}")
                                    return
                            elif "INVITE_HASH_EXPIRED" in str(e) or "not valid anymore" in str(e):
                                await update.message.reply_text('❌ 邀请链接已过期，请获取新的邀请链接')
                                logger.error(f'邀请链接已过期: {str(e)}')
                                return
                            else:
                                await update.message.reply_text(f'❌ 无法加入群组: {str(e)}')
                                logger.error(f'加入群组失败: {str(e)}')
                                return
                except Exception as e:
                    await update.message.reply_text(f'❌ 处理邀请链接时出错: {str(e)}')
                    logger.error(f'处理邀请链接时出错: {str(e)}')
                    return
            else:
                # 尝试获取群组信息
                try:
                    entity = await client.get_entity(source_chat)
                    group_name = getattr(entity, 'title', str(source_chat))
                    
                    # 尝试加入群组（如果是公开群组）
                    if hasattr(entity, 'username') and entity.username:
                        try:
                            await client(functions.channels.JoinChannelRequest(channel=entity))
                            await update.message.reply_text(f'✅ 成功加入群组 "{group_name}"')
                        except Exception as join_err:
                            if "ALREADY_PARTICIPANT" in str(join_err):
                                logger.warning(f"加入公开群组时出现非致命错误: {join_err}")
                    else:
                        await update.message.reply_text(f'未找到群组，请尝试使用邀请链接')
                except Exception as e:
                    await update.message.reply_text(f'❌ 无法获取群组信息: {str(e)}')
                    return
            
            # 获取消息数量
            limit = 50  # 默认获取50条
            
            await update.message.reply_text(f'🔍 正在获取 "{group_name}" 的历史消息...')
            
            # 获取历史消息
            messages = await client.get_messages(source_chat, limit=limit)
            
            if not messages:
                await update.message.reply_text('⚠️ 未找到历史消息，可能是因为群组为空或您没有足够的权限')
                return
                
            await update.message.reply_text(f'✅ 找到 {len(messages)} 条历史消息')
            
            # 按时间顺序转发消息（从旧到新）
            for message in reversed(messages):
                if message.text:
                    # 获取发送者信息，处理可能的None情况
                    sender_info = "未知用户"
                    if message.sender:
                        if message.sender.username:
                            sender_info = f"@{message.sender.username}"
                        elif message.sender.first_name:
                            sender_name = message.sender.first_name
                            if message.sender.last_name:
                                sender_name += f" {message.sender.last_name}"
                            sender_info = sender_name
                    
                    text = f"📜 来自 \"{group_name}\" 的历史消息:\n发送者：{sender_info}\n发送时间：\n{message.date.strftime('%Y-%m-%d %H:%M:%S')}\n内容：\n{message.text}"
                    await context.bot.send_message(
                        chat_id=target_chat,
                        text=text
                    )
                    await asyncio.sleep(1.3)  # 避免发送过快
                
                # # 如果有媒体内容，也可以处理
                # if message.media:
                #     # 下载媒体文件
                #     file_path = await message.download_media("./temp/")
                #     if file_path:
                #         try:
                #             # 根据媒体类型发送，也可以添加其他类型
                #             if message.photo:
                #                 with open(file_path, 'rb') as photo:
                #                     await context.bot.send_photo(
                #                         chat_id=target_chat,
                #                         photo=photo,
                #                         caption=f"📷 来自 \"{group_name}\" 的历史图片 | {message.text if message.text else ''}"
                #                     )
                #         except Exception as e:
                #             logger.error(f"Error sending media: {e}")
                #         finally:
                #             # 确保在任何情况下都尝试删除临时文件
                #             try:
                #                 if os.path.exists(file_path):
                #                     os.remove(file_path)
                #             except Exception as e:
                #                 logger.error(f"Error removing temporary file {file_path}: {e}")
            
            await update.message.reply_text('✅ 历史消息转发完成，正在进行分析')
            logger.info(f"Historical messages forwarded from {source_chat} ({group_name}) to {target_chat}")
            
            message_text = '\n'.join(message.text for message in messages if message.text)

            try:
                analysis = analyze_content(
                            message_text,
                            query,
                            task_type="电报群组用户发言"
                        )
                await context.bot.send_message(
                        chat_id=target_chat,
                        text=analysis
                    )
            except Exception as e:
                logger.error(f"Error analyzing historical messages: {e}")
                await update.message.reply_text(f'❌ 分析历史消息时出错: {str(e)}')
            
        except Exception as e:
            logger.error(f"Error getting historical messages: {e}")
            await update.message.reply_text(f'❌ 获取历史消息时出错: {str(e)}')

    async def list_forwards(self, update: Update, context: CallbackContext) -> None:
        """列出当前正在监听的群组"""
        if not self.forward_configs:
            await update.message.reply_text('⚠️ 当前没有任何转发配置')
            return
                
        # 过滤出当前聊天的转发配置
        target_chat = update.effective_chat.id
        logger.info(f"List forwards for chat {target_chat}")
        configs = [config for config in self.forward_configs if config['target_chat'] == target_chat]
        
        if not configs:
            await update.message.reply_text('📋 当前没有正在监听的群组')
            return
        
        message = "📋 当前转发配置：\n\n"
        for i, config in enumerate(configs, 1):
            source_chat = config['source_chat']
            group_name = config['group_name']
            config_id = config['id']
            
            # 检查处理器是否存在
            handler_status = "✅ 正常" if config_id in self.message_handlers else "❌ 未注册"
            
            message += f"{i}. 来源：{group_name}\n   ID：{source_chat}\n   状态：{handler_status}\n\n"
        
        message += "要停止监听某个群组，请使用：\n/stop_forward [群组ID]"
        await update.message.reply_text(message)
        logger.info(f"Listed {len(configs)} forwarding configurations for chat {target_chat}")

    async def stop_forward(self, update: Update, context: CallbackContext) -> None:
        """停止转发消息"""
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                '请提供要停止转发的群组ID或"all"停止所有转发：\n'
                '/stop_forward [群组ID/all]\n\n'
                '例如：\n'
                '/stop_forward -1001234567890\n'
                '/stop_forward all\n\n'
                '使用 /list_forwards 查看当前监听的群组列表'
            )
            return
        
        target_chat = update.effective_chat.id
        source_input = context.args[0].lower()
        
        # 停止所有转发
        if source_input == 'all':
            # 找出当前聊天的所有转发配置
            configs_to_remove = [config for config in self.forward_configs if config['target_chat'] == target_chat]
            
            if not configs_to_remove:
                await update.message.reply_text('📋 当前没有正在监听的群组')
                return
            
            # 移除所有处理器和配置
            for config in configs_to_remove:
                config_id = config['id']
                target_chat = config['target_chat']
                if config_id in self.message_handlers:
                    # 移除消息处理器
                    self.telethon_client.remove_event_handler(self.message_handlers[config_id])
                    del self.message_handlers[config_id]
                
                # 移除定时任务
                if target_chat in self.scheduled_jobs:
                    self.scheduled_jobs[target_chat].schedule_removal()
                    del self.scheduled_jobs[target_chat]
                    logger.info(f"Removed scheduled message analysis for {config['group_name']}")
                
                # 从配置列表中移除
                self.forward_configs.remove(config)

            # 保存配置
            self.save_forward_configs()
            # 删除消息记录
            self.group_messages = {}
            await update.message.reply_text(f'✅ 已停止所有群组的消息转发（共 {len(configs_to_remove)} 个）')
            logger.info(f"Stopped all {len(configs_to_remove)} message forwardings for chat {target_chat}")
            return
        
        # 停止特定群组的转发
        try:
            source_chat = source_input
            # 尝试转换为整数（如果是数字ID）
            try:
                source_chat = int(source_input)
            except ValueError:
                pass
            
            # 查找匹配的配置
            config_to_remove = None
            for config in self.forward_configs:
                if str(config['source_chat']) == str(source_chat) and config['target_chat'] == target_chat:
                    config_to_remove = config
                    break
            
            if not config_to_remove:
                await update.message.reply_text(f'❌ 未找到ID或名称为 "{source_input}" 的监听配置')
                return
            
            # 移除消息处理器
            config_id = config_to_remove['id']
            if config_id in self.message_handlers:
                self.telethon_client.remove_event_handler(self.message_handlers[config_id])
                del self.message_handlers[config_id]
            
            # 移除消息记录
            if config_id in self.group_messages:
                del self.group_messages[config_id]
            
            # 从配置列表中移除
            self.forward_configs.remove(config_to_remove)
            
            self.save_forward_configs()
            
            # 如果目标群组的监听任务为0则移除定时任务
            if len([config for config in self.forward_configs if config['target_chat'] == target_chat]) == 0:
                if target_chat in self.scheduled_jobs:
                    self.scheduled_jobs[target_chat].schedule_removal()
                    del self.scheduled_jobs[target_chat]
                    logger.info(f"Removed scheduled message analysis for {config_to_remove['group_name']}")
            
            await update.message.reply_text(f'✅ 已停止转发 "{config_to_remove["group_name"]}" 的消息')
            logger.info(f"Stopped message forwarding from {config_to_remove['source_chat']} to {target_chat}")
            
        except Exception as e:
            logger.error(f"Error stopping message forwarding: {e}")
            await update.message.reply_text(f'❌ 停止消息转发时出错: {str(e)}')
    
    async def post_init_callback(self, application: Application) -> None:
        """在应用程序初始化后调用"""
        if self.forward_configs:
            logger.info(f"应用程序已初始化，开始恢复消息处理器...")
            await self.restore_message_handlers()

        # 添加定时消息分析任务
        if application.job_queue:
            logger.info("正在设置定时消息分析任务...")
            
            # 为每个target_chat创建定时任务
            for config in self.forward_configs:
                source_chat = config['source_chat']
                target_chat = config['target_chat']
                group_name = config['group_name']
                config_id = config['id']
                
                # 如果target_chat已经有任务了，跳过
                if target_chat in self.scheduled_jobs:
                    continue
                
                # 确保群组消息字典已初始化
                if config_id not in self.group_messages:
                    self.group_messages[config_id] = {}
                    self.group_messages[config_id]['messages'] = []
                    self.group_messages[config_id]['group_name'] = group_name
                    
                new_job = application.job_queue.run_repeating(
                    callback=self.send_scheduled_message_analysis,
                    interval=1800,  # 每半小时执行一次分析
                    first=1800,
                    data={'target_chat': target_chat, 'source_chat': source_chat, 'group_name': group_name, 'config_id': config_id},
                    chat_id=target_chat
                )
                # 保存任务引用
                self.scheduled_jobs[target_chat] = new_job
                logger.info(f"Added scheduled message analysis for {group_name} to chat {target_chat}")
        else:
            logger.warning("应用程序的 job_queue 未初始化，无法设置定时消息分析任务")
            
    async def send_scheduled_message_analysis(self, context: CallbackContext) -> None:
        """定时分析消息并发送报告"""
        job_data = context.job.data
        target_chat = job_data.get('target_chat')
  
        messages = {} # {sc: {group_name: str, messages: [str]}}
        for config_id in self.group_messages:
            sc = config_id.split('_')[0]
            tc = config_id.split('_')[1]
            if str(tc) == str(target_chat):
                gn = self.group_messages[config_id]['group_name']
                if not messages.get(sc, None):
                    logger.info(f"初始化消息列表")
                    messages[sc] = {}
                    messages[sc]['messages'] = []
                    messages[sc]['group_name'] = gn
                messages[sc]['messages'].extend(self.group_messages[config_id]['messages'])
                # 清空对应消息列表
                self.group_messages[config_id]['messages'] = []
        
        # 获取当前UTC时间并转换为北京时间
        current_time_utc = datetime.now()
        beijing_time = current_time_utc + timedelta(hours=8)
        
        message_length = len([item for sc in messages for item in messages[sc]['messages']])
        logger.info(f"开始分析半小时内的消息，消息：{messages} 消息长度：{message_length}")
        if message_length == 0:
            await context.bot.send_message(
                chat_id=target_chat,
                text=f"⏰ 半小时消息分析\n\n时间：{beijing_time.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)\n\n最近半小时未收到任何消息，跳过分析"
            )
            return
        
        try:
            analysis = (await analyze_scheduled_messages(messages.values())).replace("```", "").replace("plaintext", "") # messages.values(): [{group_name: str, messages: [str]}]
            
            await context.bot.send_message(
                chat_id=target_chat,
                text=f'⏰ 半小时消息分析\n\n时间：{beijing_time.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)\n\n消息数量：{message_length}\n\n' + analysis
            )
            logger.info(f"分析完成，发送报告到 {target_chat}")
        except Exception as e:
            logger.error(f"Error analyzing scheduled messages: {e}")            
            
    
    def run(self, shutdown_event=None):
        """Start the Telegram bot."""
        try:
            # 创建应用实例
            application = Application.builder().token(self.token).concurrent_updates(True).build()
            # 保存应用实例
            self.application = application

            if self.bot_type == 'query':
                # Add query command handlers
                application.add_handler(CommandHandler("start", self.start))
                application.add_handler(CommandHandler("news", self.news_command))
                application.add_handler(CommandHandler("twitter_search", self.twitter_search_command))
                application.add_handler(CommandHandler("twitter_user", self.twitter_user_command))
                application.add_handler(CommandHandler("hourly", self.hourly))
                application.add_handler(CommandHandler("stop", self.stop_hourly))
                application.add_handler(CommandHandler("get_history", self.get_history))
            elif self.bot_type == 'forward':
                # Add forward command handlers
                application.add_handler(CommandHandler("start", self.start))
                application.add_handler(CommandHandler("forward_new", self.forward_new))
                application.add_handler(CommandHandler("list_forwards", self.list_forwards))
                application.add_handler(CommandHandler("stop_forward", self.stop_forward))
    
                # 启动时恢复所有已保存的转发配置的消息处理器
                if self.forward_configs:
                    logger.info(f"正在准备恢复 {len(self.forward_configs)} 个已保存的转发配置...")
                    # 使用post_init钩子在应用程序初始化后恢复消息处理器并添加定时消息分析任务
                    application.post_init = self.post_init_callback
            
            logger.info(f"Starting {self.bot_type.upper()} Telegram bot...")
            
            # 如果提供了shutdown_event，使用它来控制机器人运行
            if shutdown_event:
                application.run_polling(stop_signals=None, close_loop=False)
                while not shutdown_event.is_set():
                    time.sleep(1)
                application.stop()
            else:
                application.run_polling()
    
        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}")
            raise
        