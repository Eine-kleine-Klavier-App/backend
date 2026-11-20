-- KEYS: meta, state, record, history, deletion marker, optional author index.
-- ARGV: draft id, whether restoration must be permanently blocked.
if ARGV[2] == '1' then
    redis.call('SET', KEYS[5], '1')
end
redis.call('DEL', KEYS[1], KEYS[2], KEYS[3], KEYS[4])
if KEYS[6] then
    redis.call('SREM', KEYS[6], ARGV[1])
end
return {'ok'}
