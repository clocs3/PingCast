db = db.getSiblingDB("streaming");

db.createCollection("user_vods");

db.user_vods.createIndex({ user_id: 1, started_at: -1 });
db.user_vods.createIndex({ user_id: 1, started_at: 1 }, { unique: true });
db.user_vods.createIndex({ stream_id: 1 });
