# 直播间机器人最小闭环实施计划

> **给后续执行者：** 实现本计划时，建议按任务逐项推进。每个任务都先写测试，再写实现，完成一个小闭环后再进入下一步。

**目标：** 先构建第一版可运行闭环：启动比赛任务、生成固定测试弹幕、写入 Redis Stream、由模拟直播间消费并在页面展示。

**架构：** 当前项目采用单仓库、双服务结构。`bot_service` 负责比赛任务生命周期和 Redis 写入；`mock_live_room` 负责测试页面和 Redis 消费；`shared` 保存未来要和真实直播团队对齐的 Redis key 和消息协议。

**技术栈：** Python、FastAPI、Redis Stream、Pydantic、pytest、pytest-asyncio、fakeredis、Jinja2、Docker Compose。

---

## 一、文件结构

第一版需要创建这些文件：

```text
./
├── pyproject.toml
├── bot_service/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── live.py
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py
│   ├── integrations/
│   │   ├── __init__.py
│   │   └── redis_client.py
│   ├── personas/
│   │   ├── __init__.py
│   │   └── pool.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── live.py
│   └── services/
│       ├── __init__.py
│       ├── fake_message_generator.py
│       └── live_task_manager.py
├── mock_live_room/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── pages.py
│   ├── consumers/
│   │   ├── __init__.py
│   │   └── redis_stream_consumer.py
│   └── templates/
│       ├── index.html
│       └── room.html
├── shared/
│   ├── __init__.py
│   ├── redis_keys.py
│   └── message_contract.py
├── deploy/
│   ├── docker-compose.yml
│   └── .env.example
└── tests/
    ├── test_redis_keys.py
    ├── test_message_contract.py
    ├── test_fake_message_generator.py
    └── test_live_task_manager.py
```

## 二、实施顺序

### 任务 1：创建 Python 项目基础骨架

**要创建的文件：**

- `pyproject.toml`
- 所有目录下的 `__init__.py`

**目标：**

让项目可以被 Python 正常导入，并准备好后续依赖。

**步骤：**

1. 创建 `bot_service`、`mock_live_room`、`shared` 下的二级目录。
2. 给每个 Python 包目录添加空的 `__init__.py`。
3. 创建 `pyproject.toml`。
4. 在 `pyproject.toml` 中配置第一版依赖：
   - `fastapi`
   - `uvicorn[standard]`
   - `redis`
   - `pydantic`
   - `pydantic-settings`
   - `jinja2`
   - `httpx`
   - `pytest`
   - `pytest-asyncio`
   - `fakeredis`
5. 运行测试命令，确认项目基础结构没有导入问题。

**验收标准：**

从当前项目根目录运行测试命令时，pytest 能正常启动。

### 任务 2：实现 Redis key 命名规范

**要创建的文件：**

- `shared/redis_keys.py`
- `tests/test_redis_keys.py`

**目标：**

统一所有 Redis key 的生成规则，避免后续两个服务各自拼字符串。

**需要支持的 key：**

- `live:{matchId}:state`
- `live:{matchId}:bots`
- `live:{matchId}:messages`
- `live:{matchId}:context`
- `live:{matchId}:dedup`
- `live:{matchId}:stop`
- `live:{matchId}:stats`

**步骤：**

1. 先写测试，验证传入 `matchId=123` 时能得到上述 key。
2. 运行测试，确认测试因为模块不存在而失败。
3. 创建 `shared/redis_keys.py`。
4. 实现每个 key 对应的函数。
5. 再次运行测试，确认通过。

**验收标准：**

所有 Redis key 测试通过。

### 任务 3：实现弹幕消息协议

**要创建的文件：**

- `shared/message_contract.py`
- `tests/test_message_contract.py`

**目标：**

定义写入 Redis Stream 的弹幕消息字段，作为未来和直播团队对接的协议基础。

**消息字段：**

- `match_id`
- `bot_id`
- `bot_name`
- `content`
- `match_time`
- `event`
- `ts`

**步骤：**

1. 先写测试，验证能创建一条弹幕消息。
2. 测试消息可以转换成 Redis Stream 字段。
3. 要求转换后的字段值全部是字符串。
4. 运行测试，确认失败。
5. 创建 `ChatMessage` 模型。
6. 实现 `to_redis_fields()`。
7. 再次运行测试，确认通过。

**验收标准：**

弹幕消息字段固定，并且可以安全写入 Redis Stream。

### 任务 4：实现人设池和固定测试弹幕生成器

**要创建的文件：**

- `bot_service/personas/pool.py`
- `bot_service/services/fake_message_generator.py`
- `tests/test_fake_message_generator.py`

**目标：**

先不接 Agno 和模型，用固定测试弹幕跑通业务链路。

**人设池先保留 5 类：**

- 热血球迷
- 冷静分析
- 键盘裁判
- 新手观众
- 战术爱好者

**步骤：**

1. 先写测试，验证 `get_personas(3)` 返回 3 个机器人配置。
2. 验证每个机器人都有唯一 `bot_id`。
3. 验证生成器可以根据机器人配置生成 `ChatMessage`。
4. 验证生成的 `content` 不为空。
5. 运行测试，确认失败。
6. 实现人设池。
7. 实现固定测试弹幕生成器。
8. 再次运行测试，确认通过。

**验收标准：**

指定机器人数量后，可以生成对应数量的人设，并能生成测试弹幕。

### 任务 5：实现机器人任务管理器

**要创建的文件：**

- `bot_service/services/live_task_manager.py`
- `tests/test_live_task_manager.py`

**目标：**

实现比赛任务的核心控制能力：启动、停止、查询状态、写入一条测试弹幕。

**第一版先不实现复杂后台循环。**

**步骤：**

1. 使用 `fakeredis` 写测试。
2. 测试 `start_live(match_id="123", limit=2)` 会把比赛状态写成 `running`。
3. 测试同一个 `matchId` 重复启动时不会重复创建。
4. 测试 `stop_live("123")` 会写入停止信号。
5. 测试 `status_live("123")` 可以返回状态和统计信息。
6. 运行测试，确认失败。
7. 实现 `LiveTaskManager` 的启动、停止、状态查询。
8. 再次运行测试，确认通过。
9. 增加一个测试：调用 `write_one_fake_message("123")` 后，Redis Stream 长度变成 1。
10. 运行测试，确认失败。
11. 实现单条测试弹幕写入 Redis Stream。
12. 再次运行测试，确认通过。

**验收标准：**

任务管理器可以维护比赛状态，并向 `live:{matchId}:messages` 写入测试弹幕。

### 任务 6：实现 bot_service API

**要创建的文件：**

- `bot_service/config/settings.py`
- `bot_service/integrations/redis_client.py`
- `bot_service/schemas/live.py`
- `bot_service/api/live.py`
- `bot_service/main.py`

**目标：**

提供机器人服务的 HTTP 接口。

**接口：**

```text
GET /startLive?matchId=123456&limit=20
GET /stopLive?matchId=123456
GET /statusLive?matchId=123456
```

**步骤：**

1. 创建配置模块，读取 Redis 地址等环境变量。
2. 创建 Redis 客户端工厂。
3. 创建接口响应 schema。
4. 创建 FastAPI 路由。
5. 在 `main.py` 中注册路由。
6. 本地启动 `bot_service`。
7. 打开接口文档，确认能看到三个接口。

**验收标准：**

访问 `http://localhost:8000/docs` 时，可以看到 `startLive`、`stopLive`、`statusLive`。

### 任务 7：实现模拟直播间服务

**要创建的文件：**

- `mock_live_room/consumers/redis_stream_consumer.py`
- `mock_live_room/api/pages.py`
- `mock_live_room/templates/index.html`
- `mock_live_room/templates/room.html`
- `mock_live_room/main.py`

**目标：**

提供一个简单页面，用来在直播团队接入前测试机器人服务。

**页面能力：**

- 输入 `matchId`
- 输入 `limit`
- 调用机器人服务启动任务
- 进入模拟直播间页面
- 展示 Redis Stream 中的弹幕消息

**步骤：**

1. 实现 Redis Stream 消费器。
2. 给模拟直播间使用独立消费者组，例如 `mock-live-room`。
3. 实现首页。
4. 实现直播间页面。
5. 第一版可以先用轮询，不急着使用 SSE。
6. 创建 `mock_live_room/main.py`。
7. 本地启动模拟直播间服务。

**验收标准：**

访问 `http://localhost:8001` 能看到测试控制页面。

### 任务 8：实现 Docker Compose 本地运行环境

**要创建的文件：**

- `deploy/docker-compose.yml`
- `deploy/.env.example`

**目标：**

本地一键启动 Redis、机器人服务、模拟直播间服务。

**服务：**

- `redis`：端口 `6379`
- `bot_service`：端口 `8000`
- `mock_live_room`：端口 `8001`

**步骤：**

1. 添加 Redis 服务。
2. 添加机器人服务。
3. 添加模拟直播间服务。
4. 配置两个 Python 服务使用同一个 Redis。
5. 运行 Docker Compose。

**验收标准：**

本地可以同时访问：

- `http://localhost:8000`
- `http://localhost:8001`
- `localhost:6379`

### 任务 9：端到端验证

**目标：**

确认第一版最小闭环真的跑通。

**验证流程：**

1. 启动 Docker Compose。
2. 打开 `http://localhost:8001`。
3. 输入：
   - `matchId=demo_001`
   - `limit=3`
4. 点击启动比赛。
5. 进入模拟直播间页面。
6. 确认 Redis Stream 中消息数量增加。
7. 确认页面能展示弹幕。
8. 调用停止接口。
9. 确认任务状态变化。

**验收标准：**

- 可以启动一场比赛任务。
- 可以生成测试弹幕。
- Redis Stream 中能看到消息。
- 模拟直播间能展示消息。
- 可以停止任务。
- 不同 `matchId` 互不影响。

## 三、当前阶段不做的事情

第一版先不做：

- Agno 接入
- 小模型调用
- 体育数据 API 接入
- 语义去重
- 复杂事件驱动
- 复杂后台任务调度
- 真实直播团队消费逻辑
- 完整运营后台

这些能力等最小闭环稳定后再逐步添加。

## 四、下一步

下一步直接从 **任务 1：创建 Python 项目基础骨架** 开始。

完成任务 1 后，再进入任务 2，实现 Redis key 命名规范。
