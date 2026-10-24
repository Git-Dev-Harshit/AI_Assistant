-- Runs once, when the database volume is first created.
-- A separate database keeps the test suite from touching development data.
CREATE DATABASE knowledge_test OWNER knowledge;
