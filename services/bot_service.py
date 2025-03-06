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

# 导入Telethon相关库
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon import functions

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
    输入 /hourly [news/twitter] [特朗普/elonmusk]来设置定时推送新闻或twitter用户推文，例如："/hourly news 特朗普" 或"/hourly /twitter elonmusk"
    输入 /stop [news/twitter] 来停止定时推送

    消息转发功能：
    输入 /forward_new [源群组ID/用户名/邀请链接] 来设置消息转发
    输入 /get_history [源群组ID/用户名/邀请链接] [查询句] 来获取并分析历史消息
    输入 /list_forwards 来查看当前正在监听的群组
    输入 /stop_forward [群组ID/all] 来停止转发
    """
        self.token = token
        # Telethon客户端
        self.telethon_client = None
        # 转发配置 - 改为列表，支持多群组
        self.forward_configs = []
        # 消息处理器字典，用于管理和移除
        self.message_handlers = {}

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
            
            # 检查是否已经在监听该群组
            for config in self.forward_configs:
                if config['source_chat'] == source_chat and config['target_chat'] == target_chat:
                    await update.message.reply_text(f'⚠️ 已经在监听群组 "{group_name}"')
                    return
            
            # 创建唯一标识符
            config_id = f"{source_chat}_{target_chat}"
            
            # 设置消息处理器
            @client.on(events.NewMessage(chats=source_chat))
            async def forward_handler(event):
                """处理新消息并转发"""
                try:
                    # 获取消息内容
                    message = event.message
                    
                    # 通过机器人API发送到目标群组
                    if message.text:
                        text = f"📨 来自 \"{group_name}\" 的消息:\n\n{message.text}"
                        await context.bot.send_message(
                            chat_id=target_chat,
                            text=text
                        )
                    
                    # 如果有媒体内容，也可以处理
                    if message.media:
                        # 下载媒体文件
                        file_path = await message.download_media("./temp/")
                        if file_path:      
                            # 根据媒体类型发送，也可以添加其他类型
                            if message.photo:
                                await context.bot.send_photo(
                                    chat_id=target_chat,
                                    photo=open(file_path, 'rb'),
                                    caption=f"📷 来自 \"{group_name}\" 的图片 | {message.text if message.text else ''}"
                                )
                            
                            # 删除临时文件
                            if os.path.exists(file_path):
                                os.remove(file_path)
                            
                    logger.info(f"Message forwarded from {source_chat} ({group_name}) to {target_chat}")
                    
                except Exception as e:
                    logger.error(f"Error forwarding message via Telethon: {e}")
            
            # 保存转发配置
            config = {
                'id': config_id,
                'source_chat': source_chat,
                'target_chat': target_chat,
                'group_name': group_name
            }
            self.forward_configs.append(config)
            self.message_handlers[config_id] = forward_handler
            
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
                #         # 根据媒体类型发送，也可以添加其他类型
                #         if message.photo:
                #             await context.bot.send_photo(
                #                 chat_id=target_chat,
                #                 photo=open(file_path, 'rb'),
                #                 caption=f"📷 来自 \"{group_name}\" 的历史图片 | {message.text if message.text else ''}"
                #             )
                        
                #         # 删除临时文件
                #         if os.path.exists(file_path):
                #             os.remove(file_path)
            
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
        target_chat = update.effective_chat.id
        
        # 过滤出当前聊天的转发配置
        configs = [config for config in self.forward_configs if config['target_chat'] == target_chat]
        
        if not configs:
            await update.message.reply_text('📋 当前没有正在监听的群组')
            return
        
        message = "📋 当前正在监听的群组列表：\n\n"
        for i, config in enumerate(configs, 1):
            message += f"{i}. 群组：{config['group_name']}\n   ID：{config['source_chat']}\n\n"
        
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
                if config_id in self.message_handlers:
                    # 移除消息处理器
                    self.telethon_client.remove_event_handler(self.message_handlers[config_id])
                    del self.message_handlers[config_id]
                
                # 从配置列表中移除
                self.forward_configs.remove(config)
            
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
                if (str(config['source_chat']) == str(source_chat) or config['group_name'] == source_chat) and config['target_chat'] == target_chat:
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
            
            # 从配置列表中移除
            self.forward_configs.remove(config_to_remove)
            
            await update.message.reply_text(f'✅ 已停止转发 "{config_to_remove["group_name"]}" 的消息')
            logger.info(f"Stopped message forwarding from {config_to_remove['source_chat']} to {target_chat}")
            
        except Exception as e:
            logger.error(f"Error stopping message forwarding: {e}")
            await update.message.reply_text(f'❌ 停止消息转发时出错: {str(e)}')
    
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
            
            # 添加消息转发相关的命令处理器
            application.add_handler(CommandHandler("forward_new", self.forward_new))
            application.add_handler(CommandHandler("get_history", self.get_history))
            application.add_handler(CommandHandler("list_forwards", self.list_forwards))
            application.add_handler(CommandHandler("stop_forward", self.stop_forward))
    
            logger.info("Starting Telegram bot...")
            application.run_polling()
    
        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}")
            raise
        