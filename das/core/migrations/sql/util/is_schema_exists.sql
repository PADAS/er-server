create or replace function is_schema_exists(i_schema_name text) 
returns boolean
as
$body$
  select count(*) > 0 from pg_namespace where nspname = i_schema_name;
$body$
language sql;
