# One-API 源码分析（对标 Chameleon）

## 1. 架构总览

**技术栈**：Go (Gin 框架) 后端 + React 前端。单体应用架构，通过 GORM 操作 MySQL/PostgreSQL/SQLite。

**核心表结构**：
- `users` (id, username, quota, used_quota, group, role): 用户表，绑定 group 以支持分组计费
- `tokens` (id, user_id, key, remain_quota, used_quota, models): API 令牌表，支持按令牌配额隔离
- `channels` (id, type, key, status, weight, group, models, priority, balance, used_quota): 上游渠道表，支持权重和优先级
- `abilities` (group, model, channel_id, enabled, priority): 多维能力表 (group × model × channel)，使用联合主键实现矩阵路由
- `logs` (user_id, channel_id, model_name, quota, prompt_tokens, completion_tokens, is_stream): 消费日志表，维度完整
- `options` (key, value)：存储系统配置、模型价目表、分组倍率（JSON 格式）

表关联结构形成 **3 层路由层**：token → user → (ability) → channel，支持细粒度权限隔离和多维分配。

---

## 2. Top 5 杀手级特性分析

### 2.1 **Channel 智能路由 + Failover（最关键）**
文件：`model/ability.go:22-51`, `controller/relay.go:45-103`

**设计精妙处**：
- Ability 表用 (group, model, channel_id, priority, enabled) 联合主键建立 N:N 映射
- `GetRandomSatisfiedChannel()` 查询时先过滤 priority 最高的，再从中随机选择（`ORDER BY RANDOM()`）
- Relay 层支持自动 failover：请求失败后从相同 group/model 的其他 channel 重试，最多重试 `config.RetryTimes` 次

```go
// model/ability.go:22-40
maxPrioritySubQuery := DB.Model(&Ability{}).Select("MAX(priority)")
  .Where(groupCol+" = ? and model = ? and enabled = "+trueVal, group, model)
channelQuery = DB.Where(groupCol+" = ? and model = ? and enabled = "+trueVal+" and priority = (?)", 
  group, model, maxPrioritySubQuery)
```

**关键流程**（`relay.go:70-91`）：
1. 第一次请求失败后检查错误码，若应重试（5xx、429）则从 Ability 表中重新路由
2. 避免重复尝试同一 channel（`lastFailedChannelId` 检查）
3. 支持按 group 维度的路由独立性

**对 Chameleon 的启发**：
- Ability 表的 (group, model, channel_id, priority) 组合不仅支持"一个模型多个通道"，还支持"按优先级分层"和"按分组隔离"
- 权重（weight）可转化为概率权重（而非绝对优先级），支持 A/B 测试

### 2.2 **Token 计费系统（完整的流量计量）**
文件：`relay/billing/ratio/model.go`, `relay/controller/helper.go:60-95`, `relay/controller/helper.go:97-141`

**核心计费模型**：
```
消费 quota = (prompt_tokens + completion_tokens × completion_ratio) × model_ratio × group_ratio
```

**价目表管理**：
- `ModelRatio` 在内存中维护 600+ 模型的静态价格（`model.go:27-622`），支持 OpenAI、Claude、Gemini、Qwen 等全家桶
- 支持 channel 级别的模型映射（ModelMapping，JSON 存储在 channel 表）
- 动态更新：通过 `UpdateModelRatioByJSONString()` 支持不停机热更新
- 分组倍率存储在 `GroupRatio` 内存字典（`ratio/group.go`）

**配额扣费流程**：
1. **Pre-consume（预扣）**（`helper.go:60-95`）：
   - 基于 prompt_tokens + max_tokens 的估算，提前从 token 和 user 配额扣除
   - 若用户余额充足（> 100×preConsumedQuota），则信任用户，不预扣（避免超量锁定）

2. **Post-consume（最终扣）**（`helper.go:97-141`）：
   - 根据实际返回的 prompt_tokens 和 completion_tokens 精确计算
   - `quotaDelta = actual_quota - preConsumedQuota`，返还多余部分或继续扣除
   - 写入 Log 表记录模型倍率、分组倍率、完成度倍率

**数据扣取目标**：
- Token.remain_quota（令牌剩余额度）
- User.quota（用户剩余配额）
- 同步更新 used_quota 和 Log 表用于统计

**对 Chameleon 的启发**：
- 分离 prompt/completion 两种计费维度（通过 completion_ratio）
- 预扣机制可防止超额，条件判断避免额度锁定
- JSON 存储价目表并支持热更新，比硬编码灵活

### 2.3 **多租户 / 分组隔离（Group 维度）**
文件：`model/user.go:51`, `middleware/distributor.go:20-62`, `relay/billing/ratio/group.go`

**分组实现**：
- User 表包含 `group` 字段（VARCHAR(32)，默认 'default'）
- Channel 表也包含 `group` 字段，支持同一个上游渠道被分配给多个分组
- Ability 表的第一维就是 group，创建时 channel 的所有关联模型都被注册到该 channel 所属的所有 group 下

```go
// ability.go:53-71：channel 有多个 group，每个模型都要与每个 group 组合创建 Ability
for _, model := range models_ {
  for _, group := range groups_ {
    ability := Ability{Group: group, Model: model, ChannelId: channel.Id}
    abilities = append(abilities, ability)
  }
}
```

**分组倍率**：
- GroupRatio 内存字典（默认 default/vip/svip）支持按分组调整成本倍数
- 例：vip 分组的 gpt-4 cost 可比 default 低 50%

**路由隔离**：
- Distributor 中间件先取用户的 group，再通过 `CacheGetRandomSatisfiedChannel(userGroup, model)` 查询 Ability 表
- 不同分组的用户只能访问被分配到其分组的 channel

**对 Chameleon 的启发**：
- Group 可映射为"organization"或"team"，实现多租户隔离
- 分组在三层（User、Channel、Ability）都有体现，确保权限边界清晰

### 2.4 **Key 池管理 + 限流（Channel 级别）**
文件：`model/channel.go:20-41`, `controller/relay.go:124-132`

**Channel 设计**：
- 每个 Channel 对应一个上游 API Key（存储在 channel.Key）
- Status 字段支持四种状态：Enabled / ManuallyDisabled / AutoDisabled，实现渐进式降级
- Weight 和 Priority 支持负载均衡和优先级控制

**错误处理与自动降级**：
- `processChannelRelayError()` 监听每次请求的错误码
- 若错误表明 key 已失效或额度用尽，调用 `monitor.DisableChannel()` 自动禁用该 channel
- 下次路由时被禁用的 channel 不会被选中（status 检查）

**限流与监控**：
- Monitor 包记录 channel 的成功/失败统计
- Response time 动态更新，支持基于延迟的健康度评分

**对 Chameleon 的启发**：
- 虽然一个 channel = 一个 key，但通过 status 和自动禁用可实现"多 key 轮询"的容错效果
- 可扩展为支持多 key 池（JSON 存储）+ 轮询算法（Round-Robin）

### 2.5 **Logging & Statistics（详尽的审计日志）**
文件：`model/log.go`, `relay/controller/helper.go:126-138`

**日志维度**：
- Log 表字段：user_id, channel_id, model_name, prompt_tokens, completion_tokens, quota, is_stream, elapsed_time, system_prompt_reset
- 索引优化：(username, model_name) 复合索引、created_at 索引用于时间范围查询

**记录时机**：
- Pre-consume 前后都记录（Topup、Manage、System 类型日志）
- 每次消费请求记录：消费倍率、token 数、耗时、是否流式

**统计函数**（model/user.go, log.go）：
- `GetUserLogs(userId, logType, startTime, endTime, model, token)` 支持多维过滤
- `GetAllLogs()` 支持按 channel、model、username 聚合
- `UpdateUserUsedQuotaAndRequestCount()` + `UpdateChannelUsedQuota()` 更新聚合指标

**对 Chameleon 的启发**：
- Log 表是数据分析的基础；需要在记录时一次性写入所有维度信息，避免后期 JOIN 复杂化
- elapsed_time 可用于性能评估，is_stream 区分不同类型计费

---

## 3. 三个值得借鉴的实现模式

### 3.1 **Ability 表的矩阵路由算法**
```sql
-- 查询逻辑（model/ability.go）
SELECT * FROM abilities 
WHERE `group` = ? AND model = ? AND enabled = true
ORDER BY RANDOM() 
LIMIT 1
```

**特点**：
- 联合主键 (group, model, channel_id) 天然支持去重
- Priority 字段分层：先选最高优先级的 channel，再从中随机（避免单一 channel 过载）
- Enabled 字段快速过滤失效 channel

**Python 落地方式**（对标 Chameleon）：
```python
class Ability(Base):
    __tablename__ = 'abilities'
    group = Column(String(32), primary_key=True)
    model = Column(String(64), primary_key=True)
    channel_id = Column(Integer, ForeignKey('channels.id'), primary_key=True)
    enabled = Column(Boolean, default=True)
    priority = Column(BigInteger, default=0, index=True)

# 查询
def get_satisfied_channel(session, group, model, ignore_priority=False):
    query = session.query(Ability).filter(
        Ability.group == group,
        Ability.model == model,
        Ability.enabled == True
    )
    if not ignore_priority:
        max_priority = session.query(func.max(Ability.priority)).filter(
            Ability.group == group,
            Ability.model == model,
            Ability.enabled == True
        ).scalar()
        query = query.filter(Ability.priority == max_priority)
    
    ability = query.order_by(func.random()).first()
    return Channel.query.get(ability.channel_id)
```

### 3.2 **Pre-consume + Post-consume 的配额保护**
关键代码（`relay/controller/helper.go:68-95, 97-141`）：

**设计目标**：
- Pre-consume 预防用户透支（快速失败）
- Post-consume 精确扣费（根据实际 token 数调整）
- 信任机制：若用户余额充足，跳过预扣（避免临界情况下的锁定）

**Python 实现骨架**：
```python
async def pre_consume(user_id: int, token_id: int, prompt_tokens: int, max_tokens: int, ratio: float):
    """预扣配额"""
    pre_consumed = (config.PRE_CONSUMED_QUOTA + prompt_tokens + max_tokens) * ratio
    user_quota = await redis_client.get_user_quota(user_id)
    
    if user_quota < pre_consumed:
        raise InsufficientQuotaError()
    
    # 信任机制：余额足够则不预扣
    if user_quota > 100 * pre_consumed:
        return 0  # 跳过预扣
    
    await redis_client.decrease_user_quota(user_id, pre_consumed)
    await db.decrease_token_quota(token_id, pre_consumed)
    return pre_consumed

async def post_consume(token_id: int, user_id: int, usage: Usage, ratio: float, pre_consumed: int):
    """最终扣费"""
    model_ratio = get_model_ratio(usage.model)
    group_ratio = get_group_ratio(user.group)
    completion_ratio = get_completion_ratio(usage.model)
    
    actual_quota = int(math.ceil(
        (usage.prompt_tokens + usage.completion_tokens * completion_ratio) * 
        model_ratio * group_ratio
    ))
    
    quota_delta = actual_quota - pre_consumed
    await db.post_consume_token_quota(token_id, quota_delta)
    await log_consumption(user_id, channel_id, model, actual_quota)
```

### 3.3 **Relay 层的自适应 Failover 和降级**
代码：`controller/relay.go:45-103`, `middleware/distributor.go`

**核心流程**：
1. 第一次请求失败 → 检查错误码（5xx、429 可重试；4xx 通常不重试）
2. 若可重试，从 Ability 表随机选择不同的 channel
3. 最多重试 N 次，避免无限循环
4. 若无可用 channel，返回错误信息附加 request_id（便于日志追踪）

**状态机转移**：
```
Channel: Enabled --[error]→ AutoDisabled --[manager/manual]→ Enabled
                 --[manual disable]→ ManuallyDisabled --[manager/enable]→ Enabled
```

**Python 落地**：
```python
async def relay_with_failover(group: str, model: str, request: APIRequest, max_retries: int = 3):
    """支持自动重试的 relay"""
    last_error = None
    failed_channels = set()
    
    for attempt in range(max_retries + 1):
        try:
            channel = await get_random_satisfied_channel(group, model, ignore_failed=failed_channels)
            resp = await forward_to_channel(channel, request)
            
            if resp.status_code == 200:
                await record_channel_success(channel.id)
                return resp
            else:
                raise APIError(resp.status_code, resp.text)
                
        except APIError as e:
            last_error = e
            failed_channels.add(channel.id)
            
            if should_retry(e.status_code) and attempt < max_retries:
                logger.warning(f"Channel {channel.id} failed, retrying... ({attempt + 1}/{max_retries})")
                continue
            else:
                await disable_channel_if_fatal(channel.id, e)
                break
    
    raise RelayError(f"All retries exhausted. Last error: {last_error}")
```

---

## 4. 两个值得警惕的反模式

### 4.1 **模型价目表存内存 + 热更新不可靠**
问题：`relay/billing/ratio/model.go` 的 ModelRatio 存储在全局 map，虽支持 `UpdateModelRatioByJSONString()` 热更新，但：
- 更新时需要加锁（sync.RWMutex），高并发下读写竞争激烈
- 若更新失败（JSON 解析错误），没有 rollback 机制，新价目部分生效
- 没有版本控制，无法追溯价目变更历史

**建议**：
- 价目表应持久化到数据库（新建 Model_Pricing 表），减少内存竞争
- 更新时在事务中完成新旧版本的原子性切换

### 4.2 **Ability 表的热更新低效**
问题：`model/channel.go` 的 UpdateAbilities() 采用"先删后新增"：
```go
// 低效：删除后再插入，存在中间状态
err := channel.DeleteAbilities()  // DELETE * FROM abilities WHERE channel_id = ?
err = channel.AddAbilities()      // INSERT ...
```

**风险**：
- 高并发 GET 请求可能在中间态找不到 channel（Brief downtime）
- 大 channel（支持 100+ 模型 × 10+ 分组）的更新耗时长，阻塞路由

**建议**：
- 使用 INSERT ... ON DUPLICATE KEY UPDATE 或 UPSERT 原子操作
- 或在应用层维护"旧/新" Ability 版本，切换时原子性更新指针

---

## 5. 给 Chameleon 的三条最高优先级升级建议

### 5.1 **【立即实施】Ability 表：一个模型多个渠道的智能路由**
**当前状态**：每个 agent 绑定一个 provider，无法分发。

**升级方案**：
```sql
-- 新增表
CREATE TABLE abilities (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    group_id INT NOT NULL,          -- 用户分组
    model_code VARCHAR(64) NOT NULL, -- 如 "gpt-4", "claude-3"
    provider_id INT NOT NULL,       -- 对标 one-api 的 channel_id
    priority BIGINT DEFAULT 0,
    weight INT DEFAULT 0,           -- 负载均衡权重（0 表示平均分配）
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE KEY (group_id, model_code, provider_id),
    INDEX idx_group_model (group_id, model_code),
    FOREIGN KEY (group_id) REFERENCES groups(id),
    FOREIGN KEY (provider_id) REFERENCES providers(id)
);

-- 关键查询（附带权重路由）
SELECT provider_id FROM abilities 
WHERE group_id = ? AND model_code = ? AND enabled = true
ORDER BY priority DESC, RAND() 
LIMIT 1;
```

**实施时间**：1-2 周

**收益**：
- 一个 model_code（gpt-4）可关联多个 provider（OpenAI, Azure, Anthropic）
- 支持优先级分层和权重调度
- 自动 failover（路由失败换下一个 provider）

---

### 5.2 【核心升级】Token 计费：从"单价倍率"到"三维精准计费"**
**当前状态**：缺 quota 表、没有 model_pricing 维度、计费倍数固定。

**升级方案**：
```sql
-- 新增表 1：模型价目表（版本化）
CREATE TABLE model_pricings (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    provider_id INT NOT NULL,       -- 不同 provider 同一模型价格不同
    model_code VARCHAR(64) NOT NULL,
    input_price DECIMAL(10,6),      -- USD per 1K tokens
    output_price DECIMAL(10,6),
    completion_ratio FLOAT DEFAULT 1.0,
    version INT DEFAULT 1,          -- 版本号，支持回滚
    effective_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE KEY (provider_id, model_code, version),
    INDEX idx_provider_model (provider_id, model_code)
);

-- 新增表 2：用户配额（支持细粒度限制）
CREATE TABLE user_quotas (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    quota_limit INT64,              -- 总额度上限
    used_quota INT64 DEFAULT 0,
    remaining_quota INT64,
    reset_cycle ENUM('daily', 'monthly', 'never'),
    reset_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE KEY (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 新增表 3：消费日志（细化维度）
CREATE TABLE consumption_logs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    token_id INT,
    provider_id INT NOT NULL,
    model_code VARCHAR(64) NOT NULL,
    request_type ENUM('chat', 'image', 'embedding', 'tts'),
    prompt_tokens INT DEFAULT 0,
    completion_tokens INT DEFAULT 0,
    actual_quota INT64,
    input_price DECIMAL(10,6),
    output_price DECIMAL(10,6),
    is_stream BOOLEAN DEFAULT FALSE,
    elapsed_ms INT,
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_user_created (user_id, created_at),
    INDEX idx_provider_model (provider_id, model_code),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (provider_id) REFERENCES providers(id)
);
```

**计费流程** (Python):
```python
async def calculate_cost(model_code: str, provider_id: int, usage: Usage) -> int:
    """计算消费成本（统一单位：百万分之一 USD）"""
    pricing = await db.get_latest_model_pricing(provider_id, model_code)
    
    input_cost = usage.prompt_tokens * pricing.input_price / 1000
    output_cost = usage.completion_tokens * pricing.output_price * pricing.completion_ratio / 1000
    
    total_cost = input_cost + output_cost
    return int(total_cost * 1_000_000)  # 转为整数单位
```

**实施时间**：2-3 周

**收益**：
- 精确的按需计费（input/output 分离）
- 支持价目版本管理和回滚
- 按 provider 维度的成本差异化（OpenAI vs Azure 同一模型价格不同）

---

### 5.3 【战略升级】Group + Channel 权限隔离：多租户支持**
**当前状态**：没有 group/organization 概念，所有 agent 共享所有 provider。

**升级方案**：
```sql
-- 新增表 1：组织/分组
CREATE TABLE groups (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(64) NOT NULL,
    owner_id INT NOT NULL,          -- 组织管理员
    cost_ratio FLOAT DEFAULT 1.0,   -- 分组倍率（VIP 优惠）
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE KEY (name),
    FOREIGN KEY (owner_id) REFERENCES users(id)
);

-- 修改 users 表：加入 group_id
ALTER TABLE users ADD COLUMN group_id INT, 
    ADD FOREIGN KEY (group_id) REFERENCES groups(id);

-- 新增表 2：Group 与 Provider 的权限关系
CREATE TABLE group_provider_bindings (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id INT NOT NULL,
    provider_id INT NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE KEY (group_id, provider_id),
    FOREIGN KEY (group_id) REFERENCES groups(id),
    FOREIGN KEY (provider_id) REFERENCES providers(id)
);
```

**路由逻辑改进**：
```python
async def resolve_provider_for_request(user_id: int, model_code: str) -> Provider:
    """路由逻辑：用户 → 分组 → 关联 provider → 能力匹配"""
    user = await db.get_user(user_id)
    group = await db.get_group(user.group_id)
    
    # 获取该分组可用的 provider 列表
    allowed_providers = await db.get_group_providers(group.id, enabled=True)
    
    # 从 Ability 表中查询支持该 model_code 的 provider
    provider = await db.get_random_satisfied_provider(
        group_id=group.id,
        model_code=model_code,
        provider_ids=[p.id for p in allowed_providers]
    )
    
    return provider
```

**实施时间**：2-4 周

**收益**：
- 支持多个独立的"组织"隔离 quota、provider、日志
- 每个组织可独立管理自己的 provider 和成本倍率
- 为 SaaS 化铺路

---

## 总结对比

| 特性 | One-API | Chameleon 当前 | 建议优先级 |
|------|---------|----------------|-----------|
| 一模型多渠道路由 | ✓ (Ability 表) | ✗ | P0 |
| 按模型维度计费 | ✓ (model_ratio) | ✓ (基础) | P1 |
| 分组隔离 | ✓ (User.group) | ✗ | P1 |
| Failover 自动重试 | ✓ | 部分 | P0 |
| 版本化价目表 | 部分 | ✗ | P2 |
| 多租户支持 | 隐式 | ✗ | P2 |

---

**核心建议**：优先实现 Ability 表和 Group 隔离（P0），确保基础路由和权限框架完整后，再逐步完善计费、监控、多租户等高级特性。
