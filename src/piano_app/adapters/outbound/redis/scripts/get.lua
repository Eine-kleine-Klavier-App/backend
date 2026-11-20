-- KEYS: meta, state, record, history. A draft whose keys are not all there is corrupt
-- and removed, the same as one that was never stored.
local meta_key = KEYS[1]
local state_key = KEYS[2]
local record_key = KEYS[3]
local history_key = KEYS[4]

local keys_count = redis.call('EXISTS', meta_key, state_key, record_key, history_key)
if keys_count == 0 then
    return {'not_found'}
end
if keys_count ~= 4 then
    redis.call('DEL', meta_key, state_key, record_key, history_key)
    return {'corrupt', 'partial_keys'}
end

local version = redis.call('HGET', state_key, 'version')
if not version or tonumber(version) == nil then
    redis.call('DEL', meta_key, state_key, record_key, history_key)
    return {'corrupt', 'invalid_version'}
end
local author, title, updated_at, score =
    unpack(redis.call('HMGET', meta_key, 'author', 'title', 'updated_at', 'score'))
if not author or not title or not updated_at or not score then
    redis.call('DEL', meta_key, state_key, record_key, history_key)
    return {'corrupt', 'partial_meta'}
end

return {
    'ok',
    redis.call('GET', record_key),
    redis.call('GET', history_key),
    version,
    author,
    title,
    updated_at,
    score,
}
