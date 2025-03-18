import signal
import sys
import threading
import asyncio
from services.bot_service import TelegramBotService
from config.settings import settings

logger = settings.get_logger(__name__)

# 添加一个事件来控制线程退出
shutdown_event = threading.Event()

def handle_shutdown(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}. Initiating shutdown...")
    shutdown_event.set()  # 设置退出标志

def run_bot(bot):
    """在单独的线程中运行机器人"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # 将shutdown_event传递给bot
        bot.run(shutdown_event)
    finally:
        loop.close()

def main():
    """Main entry point for the Telegram bot application."""
    try:
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)

        # Initialize query bot
        logger.info("Initializing query Telegram bot service...")
        query_bot = TelegramBotService(token=settings.query_bot_token, bot_type="query", start_message="""
    您好！我是一个新闻搜索 Bot！
    您可以输入以下指令进行使用：

    输入 /news [查询句] 来查询新闻，例如：/news 最近的体育新闻
    输入 /twitter_search [查询句] 来查询推特，例如：/twitter 最近的中国AI新闻
    输入 /twitter_user [user id] 来查询推特用户，例如：/twitter_user elonmusk （请注意user id不是user name）
    输入 /hourly [news/twitter] [特朗普/elonmusk]来设置定时推送新闻或twitter用户推文，例如："/hourly news 特朗普" 或"/hourly /twitter elonmusk"
    输入 /stop [news/twitter] 来停止定时推送
    输入 /get_history [源群组ID/用户名/邀请链接] [查询句] 来获取并分析群组历史消息
""")

        # Initialize forward bot
        logger.info("Initializing forward Telegram bot service...")
        forward_bot = TelegramBotService(token=settings.forward_bot_token, bot_type="forward", start_message="""
    您好！我是一个消息分析与转发 Bot！
    您可以输入以下指令进行使用：

    消息转发功能：
    输入 /forward_new [源群组ID/用户名/邀请链接] 来设置消息转发
    输入 /list_forwards 来查看当前正在监听的群组
    输入 /stop_forward [群组ID/all] 来停止转发""")

        # 创建并启动两个线程
        query_thread = threading.Thread(target=run_bot, args=(query_bot,), name="QueryBot")
        forward_thread = threading.Thread(target=run_bot, args=(forward_bot,), name="ForwardBot")

        query_thread.daemon = True  # 设置为守护线程
        forward_thread.daemon = True  # 设置为守护线程

        query_thread.start()
        forward_thread.start()

        # 等待退出信号
        while not shutdown_event.is_set():
            shutdown_event.wait(1)  # 每秒检查一次退出标志

        logger.info("Shutdown signal received, stopping bots...")
        
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
    finally:
        sys.exit(0)

if __name__ == "__main__":
    main()