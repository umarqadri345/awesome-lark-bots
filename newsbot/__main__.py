# -*- coding: utf-8 -*-
"""
启动入口：python3 -m newsbot

不带参数 → 启动飞书机器人（长连接等待消息）
带 --run  → 直接生成一次日报并退出
"""

import sys


def main():
    if "--run" in sys.argv:
        sys.argv.remove("--run")
        from newsbot.run import main as run_main
        run_main()
    else:
        from newsbot.bot import main as bot_main
        bot_main()


if __name__ == "__main__":
    main()
