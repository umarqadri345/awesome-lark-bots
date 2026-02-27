#!/usr/bin/env bash
# 帮哆啦A梦把任意门卖出超级高价脑暴
# 使用前先确保 .env 中已配置 FEISHU_WEBHOOK（或在下面 export 你自己的）

set -e
cd "$(dirname "$0")"

# export FEISHU_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/你的webhook'

TOPIC='帮助哆啦A梦把任意门卖出超级高价：形成可执行、有记忆点的体验或传播方案'
CONTEXT='briefs/doraemon_anywhere_door_brainstorm.md'

python3 -m brainstorm.run --topic "$TOPIC" --context "$CONTEXT"
