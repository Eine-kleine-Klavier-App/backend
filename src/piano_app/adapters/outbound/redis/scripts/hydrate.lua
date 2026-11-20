-- Puts a draft back from the cold tier when the hot one does not hold it.
-- KEYS: meta, state, record, history, deletion marker.
-- ARGV: version, author, title, score, updated_at, ttl seconds, record, history.
local meta_key = KEYS[1]
local state_key = KEYS[2]
local record_key = KEYS[3]
local history_key = KEYS[4]

-- Deleted draft ids are never reused. A late cold read cannot resurrect their records.
if redis.call('EXISTS', KEYS[5]) == 1 then
    return {'deleted'}
end

local version = ARGV[1]
local author_id = ARGV[2]
local title = ARGV[3]
local score = ARGV[4]
local updated_at = ARGV[5]
local ttl_seconds = ARGV[6]
local record = ARGV[7]
local history = ARGV[8]

local keys_count = redis.call('EXISTS', meta_key, state_key, record_key, history_key)
if keys_count == 4 then
    return {'exists'}
end
if keys_count ~= 0 then
    redis.call('DEL', meta_key, state_key, record_key, history_key)
    return {'corrupt', 'partial_keys'}
end

redis.call('SET', record_key, record)
redis.call('SET', history_key, history)
redis.call('HSET', state_key, 'version', version)
redis.call(
    'HSET',
    meta_key,
    'author', author_id,
    'title', title,
    'updated_at', updated_at,
    'score', score
)

for i = 1, 4 do
    redis.call('EXPIRE', KEYS[i], ttl_seconds)
end

return {'ok'}
