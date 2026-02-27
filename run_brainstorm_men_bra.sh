#!/usr/bin/env bash
# 给男人卖胸罩脑暴
# 使用前先确保 .env 中已配置 FEISHU_WEBHOOK（或在下面 export 你自己的）

set -e
cd "$(dirname "$0")"

# export FEISHU_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/你的webhook'

TOPIC='如何向男性消费者有效沟通并销售胸罩（礼品/为伴侣购买等），形成可执行、有记忆点的方案'
CONTEXT='briefs/men_bra_brainstorm.md'

python3 -m brainstorm.run --topic "$TOPIC" --context "$CONTEXT"
