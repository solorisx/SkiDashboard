from centerline.geometry import Centerline
from .models import Piste, SkiArea
from shapely import Polygon

def reduce_polygon(piste: Piste):
    """
    Reduce the polygon of a piste to a line string
    :param piste: Piste object
    """

    # Get the polygon of the piste
    geom = piste.geom
    if len(geom.coords) > 4 and geom.coords[0] == geom.coords[-1]:
        polygon = Polygon(geom.coords[:-1])
        print(piste.get_osm_url())
    else:
        return
    
    # Reduce the polygon to a line string
    line = Centerline(polygon).geometry

    # Update the piste with the new line string
    piste.geom = line
    piste.save()


def reduce_ischgl_pistes():
    """
    Reduce the polygon of all Ischgl pistes to line strings
    """

    # Get all Ischgl pistes
    ischgl = SkiArea.objects.filter(name__icontains="ischgl")
    for area in ischgl:
        if area.geom:
            ischgl = area
            break
    pistes = Piste.objects.filter(geom__coveredby=ischgl.geom)

    for piste in pistes:
        reduce_polygon(piste)


def delete_all_polygon_pistes():
    """
    Delete all polygon pistes
    """

    # Get all polygon pistes
    pistes = Piste.objects.filter(geom__isnull=False)

    for piste in pistes:
        if piste.geom.coords[0] == piste.geom.coords[-1]:
            piste.delete()



