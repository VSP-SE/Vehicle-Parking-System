-- The image runs this script in POSTGRES_DB on first initialization.
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- PostgreSQL copies template1 when pytest-django creates test databases.
\connect template1
CREATE EXTENSION IF NOT EXISTS btree_gist;
