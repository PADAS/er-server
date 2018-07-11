create or replace function update_all_sequence(i_database_owner text) 
returns void
as
$body$
  select update_sequence(ns.nspname) from pg_namespace ns join pg_user u on (u.usesysid = ns.nspowner) where u.usename = i_database_owner;
$body$
language sql;
