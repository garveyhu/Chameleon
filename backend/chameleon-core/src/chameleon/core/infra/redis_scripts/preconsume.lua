-- 预扣原子脚本（P23.C3）
--
-- 在 Redis 单线程语义下原子完成"检查 in-flight 预扣余量 → 够则预扣"：
-- 把当前 reserved（在途预扣 token 数）加上本次 estimated 与 budget 比较，
-- 不超则 INCRBY reserved 并续 TTL，返回预扣后的 reserved 总量；
-- 超了不动数据，返回 -1（调用方据此判定配额不足）。
--
-- KEYS[1] = reserved key（如 chameleon:billing:reserved:{workspace_id}）
-- ARGV[1] = estimated   本次预扣的预估 token 数（> 0）
-- ARGV[2] = budget      可预扣额度 = limit - committed_used（SQL 已提交用量）
-- ARGV[3] = ttl_seconds reserved key 的过期秒数（防泄漏：请求崩了也会自动释放）
--
-- 返回：>= 0 预扣后的 reserved 总量；-1 表示会超 budget，未预扣

local reserved = tonumber(redis.call('GET', KEYS[1]) or '0')
local estimated = tonumber(ARGV[1])
local budget = tonumber(ARGV[2])

if reserved + estimated > budget then
  return -1
end

local newval = redis.call('INCRBY', KEYS[1], estimated)
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
return newval
