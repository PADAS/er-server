CREATE OR REPLACE FUNCTION update_sequence(i_schema text) 
RETURNS VOID AS 
$body$
DECLARE 
  cmd TEXT;
BEGIN
  FOR cmd IN 
    SELECT 'SELECT SETVAL(' ||
           quote_literal(quote_ident(PGT.schemaname) || '.' || quote_ident(S.relname)) ||
           ', COALESCE(MAX(' ||quote_ident(C.attname)|| '), 1) ) FROM ' ||
           quote_ident(PGT.schemaname)|| '.'||quote_ident(T.relname)|| ';'
      FROM pg_class AS S,
           pg_depend AS D,
           pg_class AS T,
           pg_attribute AS C,
           pg_tables AS PGT,
           pg_namespace AS NSP
     WHERE S.relkind = 'S'
       AND S.oid = D.objid
       AND D.refobjid = T.oid
       AND D.refobjid = C.attrelid
       AND D.refobjsubid = C.attnum
       AND T.relname = PGT.tablename
       AND PGT.schemaname = NSP.nspname
       AND S.relnamespace = NSP.oid
       AND NSP.nspname = i_schema
  LOOP
    EXECUTE cmd;
  END LOOP;
END; 
$body$
LANGUAGE plpgsql volatile;
                                                                                   