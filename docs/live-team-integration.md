# 直播团队接入说明

本文档说明直播团队如何启动机器人弹幕、停止任务、消费弹幕和查看任务状态。

## 1. 基础信息

服务：

```text
bot_service：机器人服务，提供 startLive / stopLive / statusLive
mock_live_room：测试页面和监控页面，可选
Redis：弹幕通过 Redis Stream 交付
```

默认端口：

```text
bot_service：http://{host}:8000
mock_live_room：http://{host}:8001
```

关键配置：

```text
REDIS_URL=redis://192.168.1.13:6379/2
MESSAGE_INTERVAL_SECONDS=8
MATCH_REDIS_TTL_SECONDS=86400
MAX_MATCH_RUNTIME_SECONDS=14400
```

说明：

```text
MESSAGE_INTERVAL_SECONDS：单场比赛生成弹幕的间隔，默认 8 秒
MATCH_REDIS_TTL_SECONDS：单场 Redis 数据保留时间，默认 24 小时
MAX_MATCH_RUNTIME_SECONDS：单场最长运行时间，默认 4 小时
```

## 2. 启动服务

启动机器人服务：

```powershell
uvicorn bot_service.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

可选：启动测试页面和监控页面：

```powershell
uvicorn mock_live_room.main:app --host 0.0.0.0 --port 8001 --no-access-log
```

## 3. 启动弹幕任务

接口：

```http
GET /startLive?matchId={matchId}&limit={bot数量}
```

示例：

```http
GET http://{bot_service_host}:8000/startLive?matchId=4546708&limit=8
```

参数：

```text
matchId：比赛 ID
limit：机器人数量
```

返回示例：

```json
{
  "match_id": "4546708",
  "status": "running",
  "bot_count": 8,
  "already_running": false
}
```

字段说明：

```text
already_running=false：本次新启动成功
already_running=true：该比赛已经在运行，不会重复创建任务
```

## 4. 停止弹幕任务

接口：

```http
GET /stopLive?matchId={matchId}
```

示例：

```http
GET http://{bot_service_host}:8000/stopLive?matchId=4546708
```

返回示例：

```json
{
  "match_id": "4546708",
  "stop_requested": true
}
```

说明：

```text
停止后该比赛不再生成新弹幕。
已经写入 Redis Stream 的历史弹幕不会立即删除，会按 24 小时 TTL 自动过期。
```

## 5. 查询任务状态

接口：

```http
GET /statusLive?matchId={matchId}
```

示例：

```http
GET http://{bot_service_host}:8000/statusLive?matchId=4546708
```

返回示例：

```json
{
  "match_id": "4546708",
  "state": {
    "status": "running",
    "bot_count": "8",
    "started_at": "1780827381"
  },
  "stats": {
    "sent_total": "120",
    "llm_call_total": "120",
    "llm_error_total": "0",
    "token_input": "0",
    "token_output": "0"
  },
  "queue_len": 120,
  "stop_requested": false
}
```

重点字段：

```text
state.status：任务状态
state.bot_count：机器人数量
stats.sent_total：已生成弹幕数
stats.llm_call_total：LLM 调用次数
stats.llm_error_total：LLM 调用失败次数
stats.token_input / token_output：Token 统计，取决于模型服务是否返回 usage
queue_len：Redis Stream 当前长度
stop_requested：是否已经请求停止
```

## 6. 消费弹幕

弹幕 Redis Stream key：

```text
live:{matchId}:messages
```

示例：

```text
live:4546708:messages
```

每条弹幕字段：

```text
message_id：弹幕业务唯一 ID，Redis 和 RabbitMQ 中保持一致
match_id：比赛 ID
bot_id：机器人 ID
bot_name：机器人名称
content：弹幕内容
match_time：弹幕时间描述
event：事件类型，目前固定为 live
ts：生成时间戳，秒级
```

消费端主要使用：

```text
message_id
bot_name
content
ts
```

推荐使用 Redis Stream Consumer Group。

创建消费组：

```redis
XGROUP CREATE live:{matchId}:messages live-room-team $ MKSTREAM
```

读取新弹幕：

```redis
XREADGROUP GROUP live-room-team consumer-1 COUNT 50 BLOCK 5000 STREAMS live:{matchId}:messages >
```

确认消费：

```redis
XACK live:{matchId}:messages live-room-team {messageId}
```

说明：

```text
XACK 只表示消费成功，不会删除 Stream 消息。
不建议消费后立即 XDEL，因为监控和排查问题需要读取最近弹幕。
```

## 7. 数据保留规则

以下单场 key 最多保留 24 小时：

```text
live:{matchId}:messages
live:{matchId}:state
live:{matchId}:stats
live:{matchId}:bots
live:{matchId}:stop
live:{matchId}:context
```

说明：

```text
任务运行中会自动续期。
任务停止或比赛结束后不再续期，最多 24 小时后自动过期。
messages 还会按 Stream 长度裁剪，当前单场最多约 5000 条。
```

## 8. 自动止损

系统已有自动止损：

```text
1. Nami 返回完场 / 腰斩 / 取消时，自动停止该比赛任务
2. 单场运行超过 4 小时，自动停止该比赛任务
3. 所有单场 Redis 数据最多保留 24 小时
```

如果直播团队忘记调用 stopLive，单场最多运行 4 小时。

## 9. 监控页面

如果启动了 mock_live_room，可访问：

```text
http://{mock_live_room_host}:8001/monitor
```

监控页面展示：

```text
活跃比赛数
当前任务累计弹幕数
Token 消耗
推理错误率
每场比赛运行时长
最后活跃时间
Stream 长度
异常标记
```

支持操作：

```text
停止单场比赛
停止全部比赛
手动刷新
自动刷新
```

异常标记：

```text
僵尸任务：running 但超过 10 分钟没有新弹幕
超时运行：运行超过 4 小时
高错误率：LLM 错误率超过 20%
Stream 过长：Stream 长度超过 1000
```

## 10. 常见问题

### startLive 返回 already_running=true 是什么意思？

说明该比赛已经在运行，系统不会重复创建任务。

### stopLive 后历史弹幕会消失吗？

不会立即消失。历史弹幕最多保留 24 小时。

### 消费端 XACK 后 Redis 会删除弹幕吗？

不会。XACK 只确认消费成功，消息本体仍在 Stream 中。

### Token 统计是否绝对准确？

不保证绝对准确。只有模型服务返回 usage 时，token_input / token_output 才会累计；如果服务不返回 usage，则显示为 0。

### 比赛结束后是否需要直播团队调用 stopLive？

建议调用。系统也会根据 Nami 完场状态自动停止，但直播团队主动调用 stopLive 可以更快释放任务。
