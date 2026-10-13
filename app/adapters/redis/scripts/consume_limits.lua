-- Atomic fixed window from the first hit. No bucket changes on a denial.
local retry = 0
for i, key in ipairs(KEYS) do
    local limit = tonumber(ARGV[(i-1)*2+1])
    local window = tonumber(ARGV[(i-1)*2+2])
    local count = tonumber(redis.call('GET', key) or '0')
    local ttl = redis.call('PTTL', key)
    if count >= limit then
        if ttl < 0 then ttl = window end
        retry = math.max(retry, math.max(1, math.min(ttl, window)))
    end
end
if retry > 0 then return {0, retry} end
for i, key in ipairs(KEYS) do
    local window = tonumber(ARGV[(i-1)*2+2])
    local count = redis.call('INCR', key)
    if count == 1 or redis.call('PTTL', key) < 0 then
        redis.call('PEXPIRE', key, window)
    end
end
return {1, 0}
