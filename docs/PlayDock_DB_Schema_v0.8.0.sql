-- PlayDock v0.8.0 SQLite database structure (reference only)
-- Empty DB is automatically created in data/playdock.db on first launch.

CREATE TABLE library_links (
                    game_id TEXT PRIMARY KEY,
                    raw_name TEXT NOT NULL,
                    archive_name TEXT,
                    product_code TEXT,
                    last_seen TEXT NOT NULL
                );

CREATE TABLE work_images (
                    code TEXT NOT NULL REFERENCES works(code) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    PRIMARY KEY(code, kind, position)
                );

CREATE TABLE work_tags (
                    code TEXT NOT NULL REFERENCES works(code) ON DELETE CASCADE,
                    tag TEXT NOT NULL,
                    PRIMARY KEY(code, tag)
                );

CREATE TABLE work_titles (
                    code TEXT NOT NULL REFERENCES works(code) ON DELETE CASCADE,
                    lang TEXT NOT NULL CHECK(lang IN ('ko', 'ja', 'en')),
                    title TEXT NOT NULL,
                    PRIMARY KEY(code, lang)
                );

CREATE TABLE works (
                    code TEXT PRIMARY KEY,
                    fallback_title TEXT NOT NULL,
                    maker TEXT NOT NULL DEFAULT '',
                    release_date TEXT NOT NULL DEFAULT '',
                    page_url TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    source_type TEXT NOT NULL DEFAULT '',
                    retrieved_at TEXT NOT NULL DEFAULT ''
                );

CREATE INDEX idx_library_links_code ON library_links(product_code);
