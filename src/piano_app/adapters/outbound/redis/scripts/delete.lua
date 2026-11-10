-- KEYS: revisions, state, meta, deletion marker, optional author index.
-- ARGV: draft id, whether restoration must be permanently blocked.
if ARGV[2] == '1' then
    redis.call('SET', KEYS[4], '1')
end
redis.call('DEL', KEYS[1], KEYS[2], KEYS[3])
if KEYS[5] then
    redis.call('SREM', KEYS[5], ARGV[1])
end
return {'ok'}
