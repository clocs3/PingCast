CREATE TABLE users (
    user_id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    stream_key_hash CHAR(64) UNIQUE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE user_profiles (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    nickname VARCHAR(50) NOT NULL,
    bio TEXT DEFAULT '',
    profile_image_url TEXT,
    follower_count INTEGER DEFAULT 0,
    following_count INTEGER DEFAULT 0
);

CREATE TABLE follows (
    follower_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    following_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (follower_id, following_id),
    CHECK (follower_id <> following_id)
);

CREATE TABLE games (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    name_en VARCHAR(100),
    name_ko VARCHAR(100),
    genres TEXT,
    cover_url TEXT
);

CREATE INDEX idx_users_stream_key_hash ON users(stream_key_hash);
CREATE INDEX idx_follows_following_id ON follows(following_id);
