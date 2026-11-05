-- Additive, private Wikipedia discovery inventory for Médiathèque kOA schema v4.
-- Does NOT change schema_meta/schema_version, nor create source_snapshots/representations.
-- source_registry remains the shared source authority; these are discovery edges ONLY.
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS wikipedia_discovered_pages (
    page_key TEXT PRIMARY KEY,
    source_uuid TEXT NOT NULL REFERENCES source_registry(source_uuid),
    wiki_language TEXT NOT NULL,
    page_id INTEGER NOT NULL,
    revision_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    revision_url TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    captured_json_sha256 TEXT NOT NULL,
    captured_relative_path TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL,
    discovery_scope TEXT NOT NULL,
    review_state TEXT NOT NULL DEFAULT 'unreviewed' CHECK(review_state IN ('unreviewed','reviewed','rejected')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(wiki_language,page_id,revision_id,discovery_scope)
);
CREATE INDEX IF NOT EXISTS idx_wiki_discovered_pages_scope ON wikipedia_discovered_pages(discovery_scope);
CREATE INDEX IF NOT EXISTS idx_wiki_discovered_pages_source ON wikipedia_discovered_pages(source_uuid);

CREATE TABLE IF NOT EXISTS wikipedia_discovered_links (
    occurrence_id TEXT PRIMARY KEY,
    page_key TEXT NOT NULL REFERENCES wikipedia_discovered_pages(page_key) ON DELETE CASCADE,
    target_source_uuid TEXT NOT NULL REFERENCES source_registry(source_uuid),
    observed_url TEXT NOT NULL,
    link_kind TEXT NOT NULL CHECK(link_kind IN ('citation_external','body_external','internal','navigation')),
    citation_marker TEXT,
    anchor_text TEXT,
    href_fragment TEXT,
    review_state TEXT NOT NULL DEFAULT 'unreviewed' CHECK(review_state IN ('unreviewed','reviewed','rejected')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_wiki_discovered_links_page ON wikipedia_discovered_links(page_key, link_kind);
CREATE INDEX IF NOT EXISTS idx_wiki_discovered_links_target ON wikipedia_discovered_links(target_source_uuid);
CREATE INDEX IF NOT EXISTS idx_wiki_discovered_links_kind ON wikipedia_discovered_links(link_kind);
