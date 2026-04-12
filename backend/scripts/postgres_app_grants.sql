-- Run as a PostgreSQL superuser (e.g. "postgres").
-- In pgAdmin: connect to database "bmcs" (or your DB name), open Query Tool, run the GRANT lines only.
-- In psql: you can use \c bmcs first, then the GRANTs.
--
-- Replace bmcs_app with the username from POSTGRES_URI.

GRANT USAGE, CREATE ON SCHEMA public TO bmcs_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON TABLES TO bmcs_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON SEQUENCES TO bmcs_app;

-- Optional: make the app user own the database (then public schema is manageable)
-- ALTER DATABASE bmcs OWNER TO bmcs_app;
