with cal as (select generate_series(date_trunc('day', min(created_at)), date_trunc('day', max(created_at)), '1 day'::interval) calday from activity_event),
t1 as (select cal.calday, count(e.id) from cal left join activity_event e on cal.calday = date_trunc('day', e.created_at) group by cal.calday order by cal.calday asc),
t2 as (select calday, count,
 avg(count) over (order by calday rows between 1 preceding and 1 following) mean3,
 avg(count) over (order by calday rows between 6 preceding and current row) leading7,
 avg(count) over (order by calday rows between current row and 6 following) trailing7,
 avg(count) over (order by calday rows between 3 preceding and 3 following) mean7,
 avg(count) over (order by calday rows between unbounded preceding and current row) cummean from t1)
select calday "day", count, to_char(mean3, '990.999') "3-day avg", to_char(mean7, '990.999') "7-day avg", trailing7 - leading7 "7-day trend", cummean "cum. avg" from t2;