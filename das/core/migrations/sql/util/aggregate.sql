/* Helper Functions */
CREATE OR REPLACE FUNCTION text_cat(i_text1 TEXT, i_text2 TEXT)
  RETURNS TEXT AS
$BODY$
BEGIN
  RETURN COALESCE(i_text1, '') || COALESCE(i_text2, '');
END;
$BODY$
LANGUAGE 'plpgsql' STRICT VOLATILE;

DROP AGGREGATE IF EXISTS strings(text) CASCADE;

CREATE AGGREGATE strings (
  sfunc = text_cat,
  basetype = TEXT,
  stype = TEXT,
  initcond = ''
);

DROP AGGREGATE IF EXISTS array_accum(anyarray) CASCADE;

CREATE AGGREGATE array_accum(
    BASETYPE = anyarray,
    SFUNC = array_cat,
    STYPE = anyarray
);

