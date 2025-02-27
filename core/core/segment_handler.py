import logging
from typing import List
from django.contrib.gis.geos import LineString
import osmium
import osmium.geom
from SkiingDashboardApp.osm_models import Way, Node, Aerialway, Piste, SkiArea, Station, SkiAreaBoundary, PisteSegment

logger = logging.getLogger('SkiingDashboard')

def segmentize_piste(piste: Piste) -> List[PisteSegment]:
    if piste.geom is None:
        logger.warning(f"Piste {piste.id} has no geometry.")
        return []

    # TODO: Handle reprocessing of activities
    PisteSegment.objects.filter(piste=piste).delete()

    coords = list(piste.geom.coords)
    if len(coords) < 2:
        logger.warning(f"Piste {piste.id} has too few coordinates. OSM URL: {piste.get_osm_url()}")
        segment = PisteSegment.objects.create(piste=piste, geom=piste.geom)
        return [segment]

    line: LineString = piste.geom
    
    segments = [
        PisteSegment.objects.create(piste=piste, geom=LineString([line.coords[i], line.coords[i+1]]))
        for i in range(len(line.coords) - 1)
    ]

    return segments


