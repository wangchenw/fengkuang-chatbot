# Livestream Bot 项目目标

## 项目定位

本项目用于构建一个“直播间活跃机器人”系统。直播团队在正式接入前，我方需要先维护两个服务：

- `bot_service`：机器人服务，负责创建机器人、生成直播间留言，并写入 Redis。
- `mock_live_room`：模拟直播间服务，负责测试启动任务、消费 Redis 消息，并在页面展示弹幕效果。

核心目标是先跑通完整闭环，再通过 Agno Agent 接入小模型，最后逐步接入体育数据接口。

## 核心业务目标

直播团队调用我方接口开启某一场比赛的直播暖场任务，例如：

```text
startLive?matchId=123456&limit=20
```

含义：

- `matchId` 表示单场比赛 ID。
- `limit` 表示本场比赛启动多少个机器人。
- 每个机器人拥有独立人设。
- 机器人之间互不认识，但可以基于直播间最近消息自然接话。
- 机器人不需要区分真人消息和机器人消息。
- 机器人生成的留言不直接推送到直播间，而是写入 Redis。
- 直播团队后续从 Redis 消费留言并展示到真实直播间。

## 当前推荐项目结构

```text
./
├── bot_service/              # 机器人服务
│   ├── api/                  # startLive / stopLive / statusLive
│   ├── services/             # 核心业务逻辑
│   ├── integrations/         # Redis / Agno / 模型 / 体育数据 API
│   ├── personas/             # 机器人性格配置
│   ├── schemas/              # 请求、响应、Redis 消息结构
│   └── config/               # 环境变量和配置
│
├── mock_live_room/           # 模拟直播间服务
│   ├── api/                  # 页面和测试接口
│   ├── consumers/            # Redis Stream 消费逻辑
│   └── templates/            # 简单测试页面
│
├── shared/                   # 两个服务共用的约定
│   ├── redis_keys            # Redis key 命名规范
│   └── message_contract      # 弹幕消息字段约定
│
├── docs/                     # 架构、接口、Redis 协议文档
├── deploy/                   # docker-compose、环境变量模板
└── tests/                    # 可选：端到端测试
```

当前阶段不急着拆 `domain`、`application`、`engine`、`workers`。先把核心逻辑放在 `services` 中，等调度策略、比赛上下文构建、后台任务管理变复杂后，再逐步拆分。

## 服务边界

### bot_service

只负责：

- 接收直播任务启动、停止、查询请求。
- 按 `matchId` 创建单场比赛任务。
- 按 `limit` 创建指定数量机器人。
- 给机器人分配人设。
- 构建比赛上下文。
- 通过 Agno Agent 调用小模型生成留言。
- 将留言写入 Redis Stream。
- 维护任务状态和统计数据。

不负责：

- 不直接展示直播间页面。
- 不直接对接真实直播间 UI。
- 不判断消息来自真人还是机器人。
- 不负责直播团队的消费逻辑。

### mock_live_room

只负责：

- 提供测试页面。
- 调用 `bot_service` 的启动、停止、状态接口。
- 消费 Redis Stream 中的机器人留言。
- 在页面中模拟直播间弹幕效果。

不负责：

- 不生成机器人内容。
- 不维护机器人任务。
- 不调用体育数据接口。

### shared

负责沉淀未来要和直播团队对齐的协议：

- Redis key 命名规范。
- Redis Stream 消息字段。
- 比赛任务状态枚举。
- 通用消息字段约定。

## 当前实现阶段

第一阶段已经跑通最小闭环：

```text
mock_live_room 调用 startLive
        ↓
bot_service 创建比赛任务
        ↓
bot_service 往 Redis 写测试弹幕
        ↓
mock_live_room 从 Redis 读取弹幕
        ↓
页面展示弹幕
```

当前阶段开始接入 LLM，但接入方式必须保持简单：

- 不自己实现小米 TokenPlan HTTP client。
- 统一使用 Agno 的 `Agent`。
- 模型适配使用 Agno 的 OpenAI-compatible 模型能力。
- 当前 TokenPlan 模型使用 `mimo-v2.5`，不要使用未验证可用的模型名。
- MiMo V2.5 需要通过 `extra_body={"thinking": {"type": "disabled"}}` 禁用 thinking mode，否则短弹幕场景可能只返回 reasoning 内容，最终弹幕 `content` 为空。
- 业务层只依赖 `agent.arun(...)`，不关心底层 HTTP 请求。
- 没有配置 `MIMO_API_KEY` 时，服务退回固定测试弹幕，保证 Redis 闭环仍可运行。

## Redis 设计方向

当前本地开发环境使用本机 Redis：

```text
redis://127.0.0.1:6379/2
```

远端 Redis 暂不作为默认开发依赖，避免公网连接不稳定影响本地开发和测试。

每场比赛使用 `matchId` 隔离 Redis key：

```text
live:{matchId}:state
live:{matchId}:bots
live:{matchId}:messages
live:{matchId}:context
live:{matchId}:dedup
live:{matchId}:stop
live:{matchId}:stats
```

核心队列使用 Redis Stream：

```text
live:{matchId}:messages
```

推荐每条弹幕消息包含：

- `match_id`
- `bot_id`
- `bot_name`
- `content`
- `match_time`
- `event`
- `ts`

后续直播团队只需要消费这个 Stream，不需要理解机器人服务内部实现。

## API 设计方向

当前优先保留三个接口：

```text
GET /startLive?matchId=123456&limit=20
GET /stopLive?matchId=123456
GET /statusLive?matchId=123456
```

设计原则：

- `startLive` 需要幂等，同一 `matchId` 重复启动不能创建重复任务。
- `stopLive` 只发送停止信号，具体清理由后台任务完成。
- `statusLive` 返回任务状态、机器人数量、消息数量、错误数量等基础统计。

## 体育数据接口使用优先级

对直播间活跃机器人最有价值的接口顺序：

1. 获取变动比赛列表：作为轮询入口，判断哪些比赛有更新。
2. 获取实时统计数据：核心数据源，包含比分、事件、技术统计、文字直播。
3. 获取实时比赛趋势：判断场面走势，让机器人发言更有预判感。
4. 获取比赛阵容详情：赛前调用一次，缓存球员、阵型等背景信息。
5. 获取比赛情报列表 New：赛前暖场素材，例如伤病、停赛、赛事情报。
6. 获取比赛球队统计列表：近期战绩和球队状态，适合暖场。
7. 获取比赛球员统计列表：球星话题素材，可选增强。
8. 获取比赛球队统计半全场列表：中场总结时可用。

暂时不优先使用：

- 赛程赛果列表：如果已有 `matchId`，暂时不需要。
- 单场比赛趋势详情：主要用于缺失数据补漏。
- 版权直播地址和集锦地址：与机器人留言无关。
- 实时积分榜：与单场直播活跃关系较弱。
- 删除数据接口：数据清理用途，不是机器人核心能力。

## 开发顺序

### 第一步：完成项目骨架

只创建目录和基础说明文档，不写复杂业务。

### 第二步：确定协议

先写清楚：

- API 请求和响应格式。
- Redis key 命名规则。
- Redis Stream 消息字段。
- 服务之间的职责边界。

### 第三步：跑通最小闭环

先用固定测试弹幕，不接模型：

- 启动比赛任务。
- 生成测试留言。
- 写入 Redis Stream。
- 模拟直播间消费并展示。

### 第四步：加入机器人业务逻辑

逐步加入：

- `limit` 控制机器人数量。
- 人设池。
- 随机发言节奏。
- 每场比赛独立任务。
- 停止信号。
- 去重。
- 统计数据。

### 第五步：接入 Agno 和小模型

将固定测试弹幕替换为模型生成内容：

- 每个机器人使用独立人设。
- 所有机器人共享小模型配置。
- LLM 接入必须通过 Agno Agent 标准流程。
- 不在项目内维护自定义模型 HTTP client。
- 每轮根据比赛上下文和最近消息生成一句自然弹幕。

### 第六步：接入体育数据接口

先接实时统计数据，再接趋势、阵容、情报等增强上下文。

## 当前非目标

当前阶段不做：

- 复杂后台任务平台。
- 多租户权限系统。
- 真实直播间展示系统。
- 完整运营后台。
- 复杂机器人社交关系。
- 大规模数据分析平台。

这些能力可以在最小闭环稳定后再规划。

## 判断项目成功的标准

第一阶段成功标准：

- 可以通过页面输入 `matchId` 和 `limit` 启动任务。
- Redis 中能看到该比赛的弹幕 Stream。
- 模拟直播间能实时消费并展示弹幕。
- 可以停止某场比赛任务。
- 不同 `matchId` 的任务互不影响。

第二阶段成功标准：

- 机器人发言具备不同人设。
- 发言频率自然，不刷屏。
- 关键比赛事件能触发更高活跃度。
- 弹幕内容能结合比分、时间、事件和近期聊天内容。

第三阶段成功标准：

- 直播团队只通过 Redis Stream 即可接入。
- 我方服务内部改动不影响直播团队消费协议。
- 单场比赛任务可稳定启动、运行、停止和清理。
