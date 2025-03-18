Usage: 
# 进入项目根目录
`cd telegramBot`

# 创建虚拟环境
`python -m venv venv`

# macos & linux 激活虚拟环境
`source venv/bin/activate`

# windows 激活虚拟环境
`venv\Scripts\activate`

# 安装依赖
`pip install -r requirements.txt`

# 生成Session string
`python generate_string.py` # 然后替换.env文件中的TELEGRAM_SESSION_STRING

# 替换.env文件中的QUERY_BOT_TOKEN和QUERY_BOT_TOKEN
telegram客户端搜索BotFather，然后发送/newbot指令，按照提示创建bot，然后获取token

# 运行
`python main.py`
