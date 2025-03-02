import logging
from .models import WayNode, Piste, PisteSegment

logger = logging.getLogger('core')

def update_piste_segments(osm_id=None):
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
            piste.generate_segments()
            logger.debug(f"Generated segments for piste {piste.id} - {piste.way.osm_id} - {piste.name}")
        else:
            if piste.is_geom_outdated:
                logger.debug(f"Geom for piste {piste.id} is outdated")
                old_geom = piste.geom
                new_geom = piste.update_geometry()
                if old_geom != new_geom:
                    # TODO: How to handle Activities that are associated with the piste?
                    piste.generate_segments(regenerate=True)
                    logger.debug(f"Updated geometry and segments for piste {piste.id}")
                else:
                    logger.debug(f"Geometry for piste {piste.id} is the same")