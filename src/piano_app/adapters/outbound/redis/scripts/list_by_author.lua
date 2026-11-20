-- KEYS[1] is the author's draft-id SET; every following quadruple of KEYS (grouped 4 per
-- draft, in the same order as ARGV) is that draft's own meta/state/record/history keys,
-- built by the caller
local author_drafts_key = KEYS[1]
local rows = {}

local function process_draft(draft_id, meta_key, state_key, record_key, history_key)
    local keys_count = redis.call('EXISTS', meta_key, state_key, record_key, history_key)
    if keys_count ~= 4 then
        redis.call('DEL', meta_key, state_key, record_key, history_key)
        redis.call('SREM', author_drafts_key, draft_id)
        return
    end

    local author, title, updated_at, score =
        unpack(redis.call('HMGET', meta_key, 'author', 'title', 'updated_at', 'score'))
    if not author or not title or not updated_at or not score then
        redis.call('DEL', meta_key, state_key, record_key, history_key)
        redis.call('SREM', author_drafts_key, draft_id)
        return
    end

    table.insert(rows, draft_id)
    table.insert(rows, author)
    table.insert(rows, title)
    table.insert(rows, updated_at)
    table.insert(rows, score)
end

for i, draft_id in ipairs(ARGV) do
    local base = (i - 1) * 4
    process_draft(draft_id, KEYS[base + 2], KEYS[base + 3], KEYS[base + 4], KEYS[base + 5])
end

return {'ok', unpack(rows)}
