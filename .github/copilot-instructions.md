# SkiDashboard AI Coding Guide

## Architecture Overview
SkiDashboard is a Django GIS application that tracks ski activities from Strava and matches them against OpenStreetMap ski infrastructure data. It's built around 4 core Django apps:

- **`activities`**: Strava activity import, GPS track analysis, and lift ride detection
- **`osm`**: OpenStreetMap data parsing for ski areas, lifts (aerialways), and pistes
- **`cost`**: Season pass and ticket cost tracking with value calculations  
- **`core`**: User management, settings, and shared utilities

## Key Design Patterns

### GIS-First Architecture
- Uses Django's GeoDjango with PostGIS backend (see `core/settings.py` DATABASES config)
- All spatial models inherit from `django.contrib.gis.db.models` not standard Django models
- Key spatial fields: `LineStringField` for tracks/lifts, `PointField` for stations, `MultiPolygonField` for ski areas
- Coordinate system: WGS84 (SRID 4326) for storage, local projections for calculations

### Celery Async Processing
- Activities app defines Celery instance (`activities/celery.py`) with custom JSON logging
- Heavy operations are async: Strava sync (`sync_strava_activity_task`), OSM parsing (`parse_osm_file_task`)
- Docker setup runs separate worker/beat containers for background processing
- Rate limiting on Strava API tasks: `@shared_task(rate_limit='10/m')`

### OSM Data Integration
- `osm/osm_parser.py` uses `osmium` library to process OSM files for ski infrastructure
- Filter configuration in `osm/models.py` LiftFilterConfig handles lift type exclusions globally and per-user
- OSM entities: Node → Station, Way → Aerialway/Piste, Relation → SkiArea boundaries

## Critical Development Workflows

### Local Development Setup
```bash
docker compose up -d              # Start services (PostgreSQL + Redis)
python manage.py migrate         # Apply DB migrations
python manage.py download_osm     # Download OSM ski data (large download ~500MB+)
python manage.py collectstatic    # Collect static files
```

### Testing with Real Data
- Tests in `activities/tests/` expect OSM data for realistic performance testing
- Use `--keepdb` flag to preserve expensive OSM data between test runs:
  ```bash
  python manage.py test --keepdb activities.tests.test_performance_real_data
  ```
- Performance benchmarking: `python manage.py performance_benchmark`

### Strava Integration Testing
```bash
python manage.py test_strava           # Test Strava API connection
python manage.py test_strava print     # List activities
python manage.py test_strava [activity_id]  # Test specific activity parsing
```

## Activity Processing Pipeline

The core business logic follows this flow:
1. **Strava Import** (`activities/strava_interface.py`): OAuth token management, API calls
2. **Activity Parsing** (`activities/activity_parser.py`): GPS track analysis and lift ride detection
3. **Spatial Matching**: Match GPS points to OSM aerialways using geometric intersection
4. **Cost Calculation** (`cost/seasonpass.py`): Compare lift rides against season passes

### Lift Ride Detection Algorithm
Located in `activities/activity_parser.py` - uses graph-based pathfinding:
- Build lift graph from OSM station connections
- Find closest aerialway to GPS track segments  
- Use Dijkstra's algorithm for multi-lift routes
- Apply hardcoded exceptions for known OSM data issues (see `apply_exceptions()`)

## Project-Specific Conventions

### Model Relationships
- Activities link to SkiArea via spatial intersection, not foreign keys initially
- Many-to-many through relationships: `Activity.laps` → `Lap.lift_rides` → `LiftRide.aerialway`
- Money fields use `djmoney.MoneyField` with CHF default currency

### Spatial Queries
- Use `Transform()` for projection when doing distance calculations
- Intersection queries: `activity.geom.intersects(ski_area.geom)`
- Closest aerialway: `Aerialway.objects.distance(point).order_by('distance')[:1]`

### Settings Management  
- Environment-based config via `.env` file (required for local development)
- Feature toggles: `ENABLE_SILK` for Django Silk profiling
- Separate Celery broker config: `CELERY_BROKER_URL` environment variable

### Performance Considerations
- Lift graph building is expensive - cache in parser instances  
- Spatial queries need proper indexing (handled by migrations)
- Large OSM datasets: expect 500MB+ downloads, millions of records
- Test performance with `activities/tests/test_performance_real_data.py`

## Integration Points

### External APIs
- **Strava API**: OAuth via django-allauth, token refresh in `strava_interface.py`
- **Overpass API**: OSM data download in `osm/osm_downloader.py`

### Data Dependencies  
- Requires OSM data load before meaningful activity analysis
- Strava webhook integration for real-time activity import
- Season pass data affects cost calculations retroactively

### Docker Services
- web: Django app (gunicorn)
- worker: Celery worker  
- beat: Celery scheduler
- flower: Celery monitoring (port 5555)
- db: PostGIS database
- redis: Message broker

When working with spatial data or lift matching algorithms, always consider the performance implications and test against realistic OSM datasets.