-- Install PostGIS extensions on an RDS Postgres instance
-- involves altering the owner to the RDS supplied user rds_superuser

create extension IF NOT EXISTS postgis;
create extension IF NOT EXISTS fuzzystrmatch;
create extension IF NOT EXISTS postgis_tiger_geocoder;
create extension IF NOT EXISTS postgis_topology;
-- alter schema tiger owner to rds_superuser;
alter schema topology owner to rds_superuser;
CREATE OR REPLACE FUNCTION exec(text) returns text language plpgsql volatile AS $f$ BEGIN EXECUTE $1; RETURN $1; END; $f$;
SELECT exec('ALTER TABLE ' || quote_ident(s.nspname) || '.' || quote_ident(s.relname) || ' OWNER TO rds_superuser')
  FROM (
    SELECT nspname, relname
    FROM pg_class c JOIN pg_namespace n ON (c.relnamespace = n.oid)
    WHERE nspname in ('tiger','topology') AND
    relkind IN ('r','S','v') ORDER BY relkind = 'S')
s;


-- test it
-- SET search_path=public,tiger;
-- select na.address, na.streetname, na.streettypeabbrev, na.zip from normalize_address('1 Devonshire Place, Boston, MA 02109') as na;
-- result:
-- Boston, MA 02109') as na;
--  address | streetname | streettypeabbrev |  zip
-- ---------+------------+------------------+-------
--        1 | Devonshire | Pl               | 02109
-- (1 row)