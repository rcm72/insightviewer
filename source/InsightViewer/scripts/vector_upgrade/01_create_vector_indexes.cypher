// Vector + text index setup for Chunk retrieval
// Safe to run multiple times.

CREATE CONSTRAINT chunk_id_rc_unique IF NOT EXISTS
FOR (c:Chunk)
REQUIRE c.id_rc IS UNIQUE;

CREATE FULLTEXT INDEX chunk_text_fts IF NOT EXISTS
FOR (c:Chunk)
ON EACH [c.text, c.content, c.body, c.chunkText, c.value];

CREATE VECTOR INDEX chunk_embedding_index IF NOT EXISTS
FOR (c:Chunk)
ON (c.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1024,
    `vector.similarity_function`: 'cosine'
  }
};
