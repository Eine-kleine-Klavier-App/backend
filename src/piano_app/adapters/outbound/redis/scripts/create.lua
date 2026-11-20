-- KEYS: meta, state, record, history, the author's draft-id SET.
-- ARGV: draft id, author, title, score, record, history, updated_at, ttl seconds.
local meta_key = KEYS[1]
local state_key = KEYS[2]
local record_key = KEYS[3]
local history_key = KEYS[4]
local author_drafts_key = KEYS[5]

local draft_id = ARGV[1]
local author_id = ARGV[2]
local title = ARGV[3]
local score = ARGV[4]
local record = ARGV[5]
local history = ARGV[6]
local updated_at = ARGV[7]
local ttl_seconds = ARGV[8]

local keys_count = redis.call('EXISTS', meta_key, state_key, record_key, history_key)
if keys_count == 4 then
    return {'exists'}
end
if keys_count ~= 0 then
    redis.call('DEL', meta_key, state_key, record_key, history_key)
    redis.call('SREM', author_drafts_key, draft_id)
    return {'corrupt', 'partial_keys'}
end

redis.call('SET', record_key, record)
redis.call('SET', history_key, history)
redis.call('HSET', state_key, 'version', 0)
redis.call(
    'HSET',
    meta_key,
    'author', author_id,
    'title', title,
    'updated_at', updated_at,
    'score', score
)
redis.call('SADD', author_drafts_key, draft_id)

for i = 1, 4 do
    redis.call('EXPIRE', KEYS[i], ttl_seconds)
end

return {'ok'}
