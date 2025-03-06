import sys
import time
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
from config.settings import settings
# import socks



# 从settings获取API凭据
# api_id = settings.telegram_api_id
# api_hash = settings.telegram_api_hash

api_id = '22170741'
api_hash = '056fac37f670a4a817a0a47ad31f03cd'

# 检查API凭据是否有效
if not api_id or not api_hash or api_id == 0:
    print("错误: API_ID 或 API_HASH 未设置或无效")
    print("请确保在.env文件中正确设置了TELEGRAM_API_ID和TELEGRAM_API_HASH")
    sys.exit(1)

print(f"使用API ID: {api_id}")
print(f"使用API Hash: {api_hash[:4]}...{api_hash[-4:]}")

# 设置连接参数
connection_retries = 5
retry_delay = 3  # 秒

print("\n正在尝试连接到Telegram服务器...")

# 创建客户端并设置连接参数
# proxy = {
#     'proxy_type': 'http',  # 或 'http'
#     'addr': '127.0.0.1',     # 代理服务器地址
#     'port': 7890,            # 代理服务器端口
# }

client = TelegramClient(
    StringSession(), 
    api_id, 
    api_hash,
    connection_retries=connection_retries,
    retry_delay=retry_delay,
    timeout=10,  # 增加超时时间
)

try:
    # 尝试连接
    client.connect()
    
    if not client.is_connected():
        print("无法连接到Telegram服务器，请检查您的网络连接")
        sys.exit(1)
        
    print("已成功连接到Telegram服务器")
    
    # 检查是否已经授权
    if client.is_user_authorized():
        print("您已经登录，正在生成会话字符串...")
    else:
        print("\n请登录您的Telegram账号...")
        print("提示: 如果您使用两步验证，将需要输入您的密码")
        
        # 开始登录流程
        client.start()
    
    # 生成会话字符串
    session_string = client.session.save()
    print("\n✅ 成功生成会话字符串!")
    print("\n以下是您的SESSION_STRING，请妥善保管，不要泄露给他人：")
    print("-" * 50)
    print(session_string)
    print("-" * 50)
    print("\n请将此字符串添加到.env文件中的TELEGRAM_SESSION_STRING变量")
    
except FloodWaitError as e:
    print(f"错误: Telegram限制了请求，请等待{e.seconds}秒后再试")
    sys.exit(1)
except Exception as e:
    print(f"发生错误: {e}")
    print("如果问题持续存在，请尝试以下解决方案:")
    print("1. 检查API_ID和API_HASH是否正确")
    print("2. 确保您的网络连接稳定")
    print("3. 如果您使用代理，请确保代理设置正确")
    print("4. 尝试使用不同的网络环境")
    sys.exit(1)
finally:
    # 确保客户端断开连接
    if client and client.is_connected():
        client.disconnect()
        print("已断开与Telegram服务器的连接")