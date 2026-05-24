-- 多 key 池轮转选 key（P23.C7）
--
-- 单线程语义下原子完成"round-robin 取下一个未隔离的 key index"：
-- 用一个 Redis LIST 当环形队列（元素是 key 下标 0..size-1），RPOPLPUSH 自身把队尾
-- 元素移到队首并返回 —— 连续调用即轮转。跳过在隔离集合里的下标（失败 key），最多
-- 转一圈；整池都被隔离时退而用第一个（绝不让请求拿不到 key）。
--
-- KEYS[1] = pool list（环形队列）
-- KEYS[2] = quarantine set（被隔离的失败 key 下标）
-- ARGV[1] = pool_size（channel.keys 长度）
-- ARGV[2] = ttl_seconds（刷新 list 过期）
--
-- 返回：选中的 key 下标（0..size-1）；size<=0 返 -1

local size = tonumber(ARGV[1])
if size <= 0 then
  return -1
end

-- list 长度与 pool_size 不一致（首次 / keys 变更）→ 重建为 [0..size-1]
if redis.call('LLEN', KEYS[1]) ~= size then
  redis.call('DEL', KEYS[1])
  for i = 0, size - 1 do
    redis.call('RPUSH', KEYS[1], i)
  end
end
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))

local first = nil
for _ = 1, size do
  local idx = redis.call('RPOPLPUSH', KEYS[1], KEYS[1])
  if first == nil then
    first = idx
  end
  if redis.call('SISMEMBER', KEYS[2], idx) == 0 then
    return tonumber(idx)
  end
end

-- 整池都隔离 → 退而用第一个轮到的（降级不 fail）
return tonumber(first)
