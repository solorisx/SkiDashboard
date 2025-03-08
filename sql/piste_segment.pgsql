-- select count(*) from osm_piste;
-- select count(*) from osm_piste where piste_type = 'downhill';
-- select count(*) from osm_piste where piste_type = 'nordic';


-- select osm_id, count(osm_pistesegment.id) from osm_piste
-- join osm_way on osm_piste.way_id = osm_way.id
-- left join osm_pistesegment on osm_piste.id = osm_pistesegment.piste_id
-- where osm_piste.piste_type = 'downhill'
-- group by osm_id having count(osm_pistesegment.id) = 0
-- limit 1000
-- ;

select * from osm_way
join osm_piste on osm_piste.way_id = osm_way.id
where osm_piste.id = 299909
;

select * from osm_way
where osm_way.id not in (select way_id from osm_waynode)
limit 1000
;