import logging
from .models import Piste, PisteSegment
from activities.batch import parse_strava_activity

logger = logging.getLogger('core')

def update_piste_segments(osm_id=None, force=False):
    # Update segments
    if osm_id:
        pistes = Piste.objects.filter(way__osm_id=osm_id)
    else:
        pistes = Piste.objects.all()
    for piste in pistes:
        if piste.piste_type != "downhill":
            logger.debug(f"Skipping piste {piste.id} - {piste.way.osm_id} with type {piste.piste_type}")
            continue
        if not piste.segments.all():
            logger.debug(f"No segments for piste {piste.id}")
            piste.generate_segments(regenerate=True)
            logger.debug(f"Generated segments for piste {piste.id} - {piste.way.osm_id} - {piste.name}")
        else:
            if force or piste.is_geom_outdated:
                logger.debug(f"Geom for piste {piste.id} is outdated")
                old_geom = piste.geom
                new_geom = piste.update_geometry()
                if force or old_geom != new_geom:
                    activities = PisteSegment.objects.filter(piste=piste).values("activity").distinct()
                    logger.debug(f"Affected activities: {len(activities)}")
                    piste.generate_segments(regenerate=True)
                    logger.info(f"Updated geometry and segments for piste {piste.id}")
                    for activity in activities:
                        parse_strava_activity(user=activity.user, activity_id=activity.strava_id, update=True)
                        logger.info(f"Reprocessed activity {activity.strava_id} due to update of piste segments")
                else:
                    logger.debug(f"Geometry for piste {piste.id} is the same")