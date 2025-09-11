"""Statistics calculation service for activities."""

from django.db.models import Count, F, Sum
from django.db.models.functions import Round

from activities.models import LiftRide
from osm.models import Aerialway, SkiArea


class StatisticsService:
    """Service for calculating various activity statistics."""
    
    @staticmethod
    def calculate_ski_area_statistics(activities, filter_query, user):
        """Calculate statistics grouped by ski area."""
        ski_areas = activities.values('ski_area__name').annotate(
            num_act=Count('ski_area__name'),
            ski_area_id=F('ski_area__id'),
            sum_descent=Round(Sum('total_descent'), 2),
            total_distance_km=Round((Sum('total_distance')/1000), 2),
            total_num_laps=Sum('num_laps'),
            total_num_lift_rides=Sum('num_lift_rides'),
        ).order_by('-num_act')

        # Calculate unique lift rides and progress for each ski area
        for ski_area in ski_areas:
            ski_area['total_num_dist_rides'] = StatisticsService._get_unique_lift_rides_for_ski_area(
                filter_query, user, ski_area['ski_area_id']
            )
            ski_area['total_num_area_rides'] = StatisticsService._get_total_aerialways_for_ski_area(
                ski_area['ski_area_id']
            )
            ski_area['progress'] = StatisticsService._calculate_progress(
                ski_area['total_num_dist_rides'], 
                ski_area['total_num_area_rides']
            )

        return ski_areas

    @staticmethod
    def calculate_total_statistics(activities):
        """Calculate overall activity statistics."""
        return activities.aggregate(
            total_cost=Sum('cost'),
            total_value=Sum('value'),
            sum_descent=Round(Sum('total_descent'), 2),
            total_distance_km=Round(Sum(F("total_distance"))/1000, 2),
            avg_cost=Round(Sum('cost')/Count('id'), 2),
            num_act=Count('id', distinct=True),
            total_num_laps=Sum('num_laps'),
            total_num_lift_rides=Sum('num_lift_rides'),
        )

    @staticmethod
    def aggregate_ski_area_totals(ski_areas):
        """Aggregate totals from ski area statistics."""
        num_unique_rides = sum(ski_area['total_num_dist_rides'] for ski_area in ski_areas)
        num_area_rides = sum(ski_area['total_num_area_rides'] for ski_area in ski_areas)
        
        return {
            'total_num_dist_rides': num_unique_rides,
            'total_num_area_rides': num_area_rides,
            'progress': StatisticsService._calculate_progress(num_unique_rides, num_area_rides)
        }

    @staticmethod
    def calculate_lift_ride_statistics(rides):
        """Calculate lift ride statistics."""
        lift_stats = (
            rides.values("aerialway")
            .annotate(total_rides=Count("id"))
            .order_by("-total_rides")
        )

        # Prefetch aerialways with their ski areas
        aerialways = (
            Aerialway.objects
            .filter(pk__in=[s["aerialway"] for s in lift_stats])
            .select_related("way")
            .prefetch_related("way__ski_areas")
        )
        aw_map = {aw.pk: aw for aw in aerialways}

        # Enrich lift stats with aerialway information
        for stat in lift_stats:
            aw = aw_map[stat["aerialway"]]
            stat["aerialway_name"] = aw.name
            stat["location_name"] = aw.get_location.name if aw.get_location else None

        return lift_stats

    @staticmethod
    def _get_unique_lift_rides_for_ski_area(filter_query, user, ski_area_id):
        """Get count of unique lift rides for a ski area."""
        return LiftRide.objects.filter(
            filter_query, 
            lap__activity__user=user, 
            lap__activity__ski_area__id=ski_area_id
        ).values('aerialway').distinct().count()

    @staticmethod
    def _get_total_aerialways_for_ski_area(ski_area_id):
        """Get total count of aerialways in a ski area."""
        skiarea = SkiArea.objects.get(id=ski_area_id)
        if skiarea.geom:
            return Aerialway.objects.filter(
                station_nodes__node__geom__within=skiarea.geom
            ).distinct().count()
        else:
            return Aerialway.objects.filter(
                way__in=skiarea.ways
            ).distinct().count()

    @staticmethod
    def _calculate_progress(completed, total):
        """Calculate progress percentage."""
        if total == 0:
            return 0
        return round(completed * 100.0 / total, 1)