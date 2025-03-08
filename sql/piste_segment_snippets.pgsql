-- select * from osm_pistesegment
-- where length > 1000
-- order by length desc
-- limit 1000
-- ;

-- select * from osm_piste where id = 297895;

-- select * from osm_way where id = 439990;

-- select activity_id, count(piste_segment_id), sum(length) from activities_activitypistesegment 
-- join osm_pistesegment on osm_pistesegment.id = activities_activitypistesegment.piste_segment_id
-- join activities_activity on activities_activity.id = activities_activitypistesegment.activity_id
-- group by activity_id
-- limit 1000;

-- select id, total_distance from activities_activity
-- where id = 4
-- ;


-- select count(*) from osm_pistesegment limit 1000;


select * from osm_skiarea where name like '%Ischgl%';