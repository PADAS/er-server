from django.db import migrations


forward_f = '''
CREATE or replace FUNCTION to_numeric(numeric) RETURNS numeric
    LANGUAGE plpgsql IMMUTABLE
    AS $_$
begin
    return $1;
exception
    when others then
    return null;
end;
$_$;


CREATE or REPLACE FUNCTION to_numeric(text) RETURNS numeric
    LANGUAGE plpgsql IMMUTABLE
    AS $_$
begin
    return case when $1 is null then null
         else cast($1 as numeric)
    end;
exception
    when invalid_text_representation then
        return null;
    when others then
        return null;
end;
$_$;
'''

reverse_f = '''
drop function if exists to_numeric(numeric);
drop function if exists to_numeric(text);
'''


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0081_auto_20191104_2326'),
    ]

    operations = [
        migrations.RunSQL(sql=forward_f, reverse_sql=reverse_f),
    ]
