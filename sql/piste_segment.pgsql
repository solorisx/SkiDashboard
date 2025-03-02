-- select count(*) from osm_piste;
-- select count(*) from osm_piste where piste_type = 'downhill';
-- select count(*) from osm_piste where piste_type = 'nordic';


select osm_id, count(osm_pistesegment.id) from osm_piste
join osm_way on osm_piste.way_id = osm_way.id
left join osm_pistesegment on osm_piste.id = osm_pistesegment.piste_id
where osm_piste.piste_type = 'downhill'
group by osm_id having count(osm_pistesegment.id) = 0
limit 1000
;