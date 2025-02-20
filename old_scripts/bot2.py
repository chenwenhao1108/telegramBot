import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext, ContextTypes
from test import news_agent, news_prompt, gpt_infer, analyze_news_prompt, get_x_posts
import telegram


start_message = """
您好！我是一个新闻搜索 Bot！
您可以输入以下指令进行使用：

输入 /news 命令来查询新闻，例如：/news 最近的体育新闻
输入 /twitter 命令来查询推特，例如：/twitter 最近的中国AI新闻
输入 /hourly 新闻关键词' 来设置定时推送新闻
输入 /stop  来停止定时推送
"""

async def start(update: Update, context: CallbackContext) -> None:

    await update.message.reply_text(start_message)

async def twitter_command(update: Update, context: CallbackContext) -> None:
    # 检查是否有提供参数
    if not context.args:
        await update.message.reply_text('请在 /twitter 命令后输入您的问题，例如：/twitter 最近的体育新闻')
        return
    
    query = ' '.join(context.args)
    print(f'用户正在查询：{query}')
    
    await update.message.reply_text(f'正在查询：{query}，请稍等...')

    max_retries= 3
    for retry in range(max_retries):
        tweets = await get_x_posts(query, date = datetime.now().strftime("%Y-%m-%d"))
        if not isinstance(tweets, list):
            await update.message.reply_text(f"查询结果格式不正确，正在重试...({retry + 1}/{max_retries})")
            continue
        
        if len(tweets) == 0:
            await update.message.reply_text("找到0篇相关推文。请尝试换个话题或拉长时间间隔，如：/twitter 最近一周有哪些体育新闻")
            return
        else:
            for tweet in tweets:
                try:
                    await update.message.reply_text(text=tweet)
                    await asyncio.sleep(0.5)
                except telegram.error.RetryAfter as e:
                    # 遇到限流时等待指定时间
                    await asyncio.sleep(e.retry_after)
                    await update.message.reply_text(text=tweet)
                    
            try:
                formatted_tweets = "\n\n".join(tweets)
                res = gpt_infer(analyze_news_prompt.replace("{news_list}", formatted_tweets).replace("{user_question}", query).replace("{task_type}", "推特帖子"))
                await update.message.reply_text(text=res)
            except Exception as e:
                print(f"分析新闻失败: {e}")
                await update.message.reply_text("推文分析失败，但已为您展示所有新闻")
            return


async def news_command(update: Update, context: CallbackContext) -> None:
    # 检查是否有提供参数
    if not context.args:
        await update.message.reply_text('请在 /bot 命令后输入您的问题，例如：/bot 最近的体育新闻')
        return
    
    query = ' '.join(context.args)
    
    await update.message.reply_text(f'正在查询：{query}，请稍等...')
    
    max_retries = 3
    for retry in range(max_retries):
        try:
            task = news_prompt.replace("{topic}", query).replace(
                "{date}", datetime.now().strftime("%Y-%m-%d")   
            )
            news_items = news_agent.run(task)
            
            if not isinstance(news_items, list):
                await update.message.reply_text(f"查询结果格式不正确，正在重试...({retry + 1}/{max_retries})")
                continue
            
            news_count = len(news_items)
            if news_count > 0:
                try:
                    await update.message.reply_text(f'获取到了最近{news_count}条新闻')
                    
                    # 添加延时，避免触发限流
                    for article in news_items:
                        try:
                            await update.message.reply_text(text=article)
                            await asyncio.sleep(0.5)  # 每条消息之间添加短暂延时
                        except telegram.error.RetryAfter as e:
                            # 遇到限流时等待指定时间
                            await asyncio.sleep(e.retry_after)
                            await update.message.reply_text(text=article)
                    
                    try:
                        formatted_news = "\n\n".join(news_items)
                        res = gpt_infer(analyze_news_prompt.replace("{news_list}", formatted_news).replace("{user_question}", query).replace("{task_type}", "新闻"))
                        await update.message.reply_text(text=res)
                    except Exception as e:
                        print(f"分析新闻失败: {e}")
                        await update.message.reply_text("新闻分析失败，但已为您展示所有新闻")
                    
                except telegram.error.RetryAfter as e:
                    print(f"触发Telegram限流，需要等待 {e.retry_after} 秒")
                    await asyncio.sleep(e.retry_after)
                    await update.message.reply_text("消息发送过快，正在重试...")
                except Exception as e:
                    print(f"发送消息时出错: {e}")
                    await update.message.reply_text("发送消息时出错，请稍后重试")
                
                return
            else:
                if retry == max_retries - 1:
                    await update.message.reply_text("抱歉，经过多次尝试仍未能找到相关新闻。请尝试换个话题或稍后再试。")
                else:
                    await update.message.reply_text(f"未查询到新闻，正在重试 {retry + 1}/{max_retries}")
        except Exception as e:
            if retry < max_retries - 1:
                await update.message.reply_text(f"查询失败，正在重试...({retry + 1}/{max_retries})")
            else:
                await update.message.reply_text(f"抱歉，查询出错：{str(e)}")
                print(f"查询失败: {e}")


async def send_scheduled_message(context: ContextTypes.DEFAULT_TYPE):
    """定时任务回调，发送消息"""
    job_data = context.job.data
    query = job_data['message'] + ' in recent 1 hour'
    
    max_retries = 3
    for retry in range(max_retries):
        try:
            task = news_prompt.replace("{topic}", query).replace(
                "{date}", datetime.now().strftime("%Y-%m-%d")   
            )
            news_items = news_agent.run(task)
            if not isinstance(news_items, list):
                print(f"返回的内容不是列表，类型为: {type(news_items)}，进入下一轮循环")
                await context.bot.send_message(
                    chat_id=job_data['chat_id'],
                    text=(f"查询结果格式不正确，正在重试...({retry + 1}/{max_retries})")
                )
                continue
            
            news_count = len(news_items)
            if(news_count > 0):
                try:
                    await context.bot.send_message(
                        chat_id=job_data['chat_id'],
                        text=f'Hourly news： {query}'
                    )
                    for article in news_items:
                        try:
                            await context.bot.send_message(
                                chat_id=job_data['chat_id'],
                                text=article
                            )
                            await asyncio.sleep(0.5)  # 每条消息之间添加短暂延时
                        except telegram.error.RetryAfter as e:
                            # 遇到限流时等待指定时间
                            print(f"触发限流，等待 {e.retry_after} 秒")
                            await asyncio.sleep(e.retry_after)
                            await context.bot.send_message(
                                chat_id=job_data['chat_id'],
                                text=article
                            )
                        except Exception as e:
                            print(f"发送消息时出错: {e}")
                            continue
                except Exception as e:
                    print(f"发送消息时发生错误: {e}")
                    await context.bot.send_message(
                        chat_id=job_data['chat_id'],
                        text="发送消息时出错，请稍后重试"
                    )
                break
            else:
                if retry == max_retries - 1:
                    await context.bot.send_message(
                    chat_id=job_data['chat_id'],
                    text=f"最近一小时并无关于{query}的新闻"
                    )
        except Exception as e:
            print('获取新闻时出错，正在重试')
            continue

async def hourly_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_message = ' '.join(context.args).strip()
    
    if not user_message:
        await update.message.reply_text("⚠️ 请提供要监听的新闻内容，例如：/hourly 特朗普")
        return
    
    # 若存在旧任务，先移除
    if 'job' in context.chat_data:
        old_job = context.chat_data['job']
        old_job.schedule_removal()
    
    new_job = context.job_queue.run_repeating(
        callback=send_scheduled_message,
        interval=3600,  # 发送间隔
        first=10,     # 首次执行延迟10秒，避免立即触发
        data={'message': user_message, 'chat_id': chat_id},
        chat_id=chat_id
    )
    
    context.chat_data['job'] = new_job  # 存储任务到当前聊天数据
    await update.message.reply_text(f"✅ 开始每小时推送关于：{user_message} 的新闻")
    
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'job' in context.chat_data:
        context.chat_data['job'].schedule_removal()
        del context.chat_data['job']
        await update.message.reply_text("已停止Hourly news。")
    else:
        await update.message.reply_text("请先开启Hourly news： /hourly 特朗普")

def main():
    # server bot:
    # application = Application.builder().token("8029538453:AAGX6ZGOPxMQheOQorljGKEai32iYkAyV-A").build()
    
    # local test bot:
    application = Application.builder().token("7985592178:AAGDhjZSRDTEvrfuZNa3lVYBwyfbqb9c4yU").build()

    # 添加命令处理器
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("news", news_command))
    application.add_handler(CommandHandler("twitter", twitter_command))
    application.add_handler(CommandHandler("hourly", hourly_news))
    application.add_handler(CommandHandler("stop", stop))

    # 添加消息处理器
    # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_command))

    application.run_polling()

if __name__ == '__main__':
    main()
