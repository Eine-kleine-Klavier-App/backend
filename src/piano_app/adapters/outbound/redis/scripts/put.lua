-- Replaces a draft's record, history and state when its stored version is the expected one.
-- A draft that vanished (TTL, eviction) is reported as not found so the tiered adapter can
-- bring it back from cold.
-- KEYS: meta, state, record, history.
-- ARGV: expected version, new version, record, history, updated_at, ttl seconds.
local meta_key = KEYS[1]
local state_key = KEYS[2]
local record_key = KEYS[3]
local history_key = KEYS[4]

local expected_version = ARGV[1]
local new_version = ARGV[2]
local record = ARGV[3]
local history = ARGV[4]
local updated_at = ARGV[5]
local ttl_seconds = ARGV[6]

local keys_count = redis.call('EXISTS', meta_key, state_key, record_key, history_key)
if keys_count == 0 then
    return {'not_found'}
end
if keys_count ~= 4 then
    redis.call('DEL', meta_key, state_key, record_key, history_key)
    return {'corrupt', 'partial_keys'}
end

local current_version = redis.call('HGET', state_key, 'version')
if not current_version or tonumber(current_version) == nil then
    redis.call('DEL', meta_key, state_key, record_key, history_key)
    return {'corrupt', 'invalid_version'}
end
if tonumber(current_version) ~= tonumber(expected_version) then
    return {'conflict'}
end

redis.call('SET', record_key, record)
redis.call('SET', history_key, history)
redis.call('HSET', state_key, 'version', new_version)
redis.call('HSET', meta_key, 'updated_at', updated_at)

for i = 1, 4 do
    redis.call('EXPIRE', KEYS[i], ttl_seconds)
end

return {'ok'}
