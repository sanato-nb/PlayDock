-- PlayDock SQLite v3: ONE active DB at <installed PlayDock>/data/playdock.db
-- Runtime migration from v1/v2 preserves works, local links and any scanner
-- official_works rows in a SQLite transaction after a verified backup.
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS works (
    store TEXT NOT NULL,             -- dlsite / steam
    code TEXT NOT NULL,              -- RJ... / Steam App ID
    title TEXT NOT NULL,             -- official work title
    category TEXT NOT NULL DEFAULT '',
    maker TEXT NOT NULL DEFAULT '',
    page_url TEXT NOT NULL DEFAULT '',
    checked_at TEXT NOT NULL DEFAULT '',
    titles_json TEXT NOT NULL DEFAULT '{}',
    tags_json TEXT NOT NULL DEFAULT '[]',
    images_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (store, code)
);

CREATE TABLE IF NOT EXISTS library_links (
    game_id TEXT PRIMARY KEY,       -- local game identifier
    store TEXT NOT NULL DEFAULT '', -- user-selected storefront
    code TEXT NOT NULL DEFAULT ''   -- user-selected work code
);

CREATE INDEX IF NOT EXISTS idx_links_site_code
    ON library_links(store, code);

PRAGMA user_version=3;
