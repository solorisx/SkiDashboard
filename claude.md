# SkiDashboard - Claude Development Guide

## Project Overview

SkiDashboard is a sophisticated Django GIS web application that tracks ski activities, analyzes GPS tracks to detect lift rides and piste runs, and provides comprehensive statistics and insights. The application integrates with Strava for activity syncing and uses OpenStreetMap data for ski infrastructure mapping.

**Key Technologies:**
- Django 5.2.6 with GeoDjango
- PostgreSQL 16 with PostGIS 3.4
- Celery 5.5.1 + Redis 7 for async tasks
- Python 3.11
- Docker & Docker Compose

## Quick Start

### Prerequisites
- Docker and Docker Compose installed
- Python 3.11 (for local development outside Docker)

### Development Setup

**IMPORTANT:** This project uses Docker for both local and production deployment.

1. **Clone and enter the repository:**
   ```bash
   cd /home/sascha/VSCode/SkiDashboard
   ```

2. **Set up environment variables:**
   - Copy `.env.example` to `.env` (if exists) or create `.env` with required variables
   - Essential variables: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`

3. **Start with Docker:**
   ```bash
   docker-compose up -d
   ```

   This starts:
   - Web service (Django) on port 8000
   - Worker service (Celery)
   - Beat service (Celery scheduler)
   - Flower (monitoring) on port 5555
   - PostgreSQL with PostGIS
   - Redis

4. **Access the application:**
   - Web: http://localhost:8000
   - Flower (Celery monitoring): http://localhost:5555
   - Admin: http://localhost:8000/admin/

### Local Development (Outside Docker)

**CRITICAL: Use `python3` not `python`**

1. **Activate virtual environment FIRST:**
   ```bash
   source venv/bin/activate  # or create with: python3 -m venv venv
   ```

2. **Install dependencies:**
   ```bash
   python3 -m pip install -r requirements.txt
   ```

3. **Before creating migrations, ALWAYS activate venv:**
   ```bash
   source venv/bin/activate
   python3 manage.py makemigrations
   python3 manage.py migrate
   ```

4. **Run development server:**
   ```bash
   python3 manage.py runserver
   ```

5. **Run Celery worker (separate terminal):**
   ```bash
   source venv/bin/activate
   celery -A core worker -l info
   ```

6. **Run Celery beat (separate terminal):**
   ```bash
   source venv/bin/activate
   celery -A core beat -l info
   ```

## Project Structure

```
SkiDashboard/
├── core/                    # User management, auth, settings
│   ├── models.py           # UserProfile
│   ├── settings.py         # Django configuration
│   ├── strava_adapter.py   # Custom Strava OAuth
│   ├── account_adapter.py  # Async email adapter
│   ├── signals.py          # User signup signals
│   └── tasks.py            # Core Celery tasks
│
├── activities/             # Strava integration & GPS analysis
│   ├── models.py          # Activity, Lap, Record, LiftRide, Badge
│   ├── activity_parser.py # GPS track analysis (~1700 lines)
│   ├── strava_interface.py # Strava API client
│   ├── tasks.py           # Async Strava sync
│   ├── badges.py          # Badge logic
│   ├── signals.py         # Cache invalidation
│   ├── views/
│   │   ├── activity.py    # Activity list, detail, map
│   │   ├── api.py         # API endpoints
│   │   ├── insights.py    # Statistics
│   │   ├── sync.py        # Strava sync views
│   │   └── webhook.py     # Strava webhooks
│   └── utils/
│       ├── completeness.py # Ski area completeness
│       ├── image_generator.py # Share images
│       └── seasons.py     # Season management
│
├── osm/                   # OpenStreetMap integration
│   ├── models.py         # Aerialway, Piste, SkiArea, Station
│   ├── osm_parser.py     # OSM file parsing (~640 lines)
│   ├── osm_downloader.py # Overpass API client
│   ├── osm_interface.py  # OSM data loading
│   └── tasks.py          # OSM processing tasks
│
├── cost/                  # Season pass tracking
│   ├── models.py         # TicketPrice, SeasonPass
│   ├── prices.py         # Price calculations
│   └── seasonpass.py     # Season pass validation
│
├── static/               # Custom CSS, JS, images
├── staticfiles/          # Collected static files
├── media/                # User uploads
├── locale/               # i18n files
├── sql/                  # SQL scripts
└── tmp/                  # Temporary files
```

## Database Models

### Core App
- **UserProfile**: User preferences (language, timezone, units, excluded lift types, season boundaries)

### Activities App
- **Activity**: Main activity record with GPS data, Strava integration
- **Lap**: Activity segments with lift rides
- **Record**: Individual GPS points (PostGIS geometry)
- **LiftRide**: Activity-to-aerialway associations
- **PisteRide**: Piste usage tracking
- **Badge**: Achievement definitions
- **ActivityBadge**: User badge assignments
- **StravaSyncSettings**: Global sync configuration

### OSM App
- **Node**: OSM nodes (base spatial entity)
- **Way**: OSM ways (paths/areas)
- **Station**: Lift stations
- **Aerialway**: Ski lifts (capacity, duration, heating)
- **Piste**: Ski runs (difficulty, grooming, lighting)
- **PisteSegment**: Piste sub-segments
- **SkiArea**: Ski resort boundaries and metadata
- **SkiAreaNetwork**: Ski pass networks (Epic Pass, etc.)

### Cost App
- **TicketPrice**: Day/season pass pricing
- **SeasonPass**: User season pass records

## Key API Endpoints

### Activity Management
- `GET /activities/` - Activity list
- `GET /activities/<id>/` - Activity detail
- `GET /activities/<id>/map/` - Activity map view
- `POST /activities/<id>/reprocess/` - Reprocess activity
- `POST /activities/sync_strava/` - Manual Strava sync
- `POST /activities/strava/webhook/` - Strava webhook

### Insights
- `GET /activities/insights/` - Activity insights
- `GET /activities/lift-insights/` - Lift-specific analytics
- `GET /activities/piste-insights/` - Piste-specific analytics
- `GET /activities/ski-area-completeness/` - Completeness tracking

### API Endpoints
- `GET/POST/PATCH/DELETE /api/lift-ride/` - Lift ride CRUD
- `DELETE /api/piste-ride/<id>/` - Delete piste ride
- `GET/POST/PATCH/DELETE /api/season-pass/` - Season pass management
- `GET /api/season-stats/` - Season statistics
- `POST /api/activity/<id>/` - Update activity
- `POST /api/update-strava-description/<id>/` - Update Strava description

### OSM Admin
- `POST /osm/admin/sync-osm-api/` - Sync from Overpass API
- `POST /osm/admin/sync-osm-file/` - Sync from OSM file
- `GET /osm/skiarea-autocomplete/` - Ski area autocomplete

## Architecture & Key Features

### GIS-First Design
- All spatial operations use PostGIS with WGS84 (SRID 4326)
- Spatial indexing on Activity, Aerialway, Piste models
- Distance and intersection queries for matching GPS tracks to infrastructure

### Activity Processing Pipeline
1. **Strava API** → Activity import via webhook or scheduled sync
2. **GPS track analysis** → Lap detection, turning points
3. **Spatial matching** → Identify lifts and pistes using PostGIS
4. **Cost calculation** → Season pass value analysis
5. **Badge assignment** → Achievement tracking

### Strava Integration
- OAuth with dynamic scopes (read, activity:read_all, activity:write optional)
- Automatic token refresh
- Webhook-based real-time sync
- Scheduled sync via Celery beat
- Two-way sync: can update Strava activity descriptions

### Lift Ride Detection Algorithm
Located in [activities/activity_parser.py](activities/activity_parser.py):
- Graph-based turning point detection
- Spatial matching to known lift infrastructure
- Speed and altitude-based filtering
- Multi-lift route analysis
- Station network matching

### Caching Strategy
- Database-backed cache with 15-minute timeout
- Per-activity completeness caching
- Per-ski-area statistics caching
- Signal-based invalidation on activity changes

### Badge System
Achievements include:
- Lift-based: specific lift rides, lifetime lifts
- Elevation: vertical meters in day/lifetime
- Exploration: ski area completeness
- Rarity levels: bronze, silver, gold, platinum, legendary

## Common Development Tasks

### Database Migrations

**ALWAYS activate venv first!**

```bash
source venv/bin/activate
python3 manage.py makemigrations
python3 manage.py migrate
```

### Reprocess Activities

```bash
python3 manage.py reprocess --all  # Reprocess all activities
python3 manage.py reprocess <id>   # Reprocess specific activity
```

### Download OSM Data

```bash
python3 manage.py download_osm <ski_area_id>
```

### Update Piste Segments

```bash
python3 manage.py update_segments
```

### Test Strava Integration

```bash
python3 manage.py test_strava
```

### Run Tests

```bash
python3 manage.py test
python3 manage.py test --keepdb  # Keep OSM data between runs
```

### Collect Static Files

```bash
python3 manage.py collectstatic --noinput
```

### Create Superuser

```bash
python3 manage.py createsuperuser
```

### Access Django Shell

```bash
python3 manage.py shell
```

## Configuration

### Environment Variables (.env)

**Database:**
- `DATABASE_URL` - PostgreSQL connection string (must have PostGIS)

**Redis:**
- `REDIS_URL` - Redis connection for Celery and cache

**Django:**
- `SECRET_KEY` - Django secret key
- `DEBUG` - Debug mode (True/False)
- `ALLOWED_HOSTS` - Comma-separated allowed hosts
- `CSRF_TRUSTED_ORIGINS` - Comma-separated origins

**Strava:**
- `STRAVA_CLIENT_ID` - Strava OAuth client ID
- `STRAVA_CLIENT_SECRET` - Strava OAuth secret

**Email (Mailgun):**
- `MAILGUN_API_KEY`
- `MAILGUN_SENDER_DOMAIN`
- `DEFAULT_FROM_EMAIL`

**Email (SMTP fallback):**
- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS`

**Optional:**
- `ENABLE_SILK` - Enable Django Silk profiling (True/False)
- `LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)
- `LOG_FORMATTER` - Logging format (verbose, json)

### Database Configuration

PostGIS is required. The app auto-detects cloud databases and adjusts settings.

**Local development:**
```bash
docker-compose up db  # Starts PostGIS container
```

**Connection string format:**
```
postgresql://user:password@host:port/dbname
```

### Celery Configuration

**Broker:** Redis (configured via `REDIS_URL`)

**Scheduled Tasks (Beat):**
- Strava sync: Periodic (configurable interval)
- Badge recalculation: Daily
- Cache cleanup: Hourly

**Workers:**
- Default queue: Activity processing
- Priority queue: Strava sync
- Low priority: Badge recalculation

## Testing

### Test Structure
- Tests in `*/tests/` directories
- Activity parser has comprehensive test suite
- Use `--keepdb` to preserve OSM data between runs

### Running Tests
```bash
python3 manage.py test                    # All tests
python3 manage.py test activities         # App-specific
python3 manage.py test --keepdb          # Preserve data
python3 manage.py test --parallel        # Parallel execution
```

## Deployment

### Docker Production

1. **Build image:**
   ```bash
   docker build -t skidashboard .
   ```

2. **Run with docker-compose:**
   ```bash
   docker-compose up -d
   ```

3. **Migrations are automatic** via [start.sh](start.sh)

### Environment Considerations

**Cloud platforms (Render, Railway, etc.):**
- Set `DATABASE_URL` with PostGIS database
- Set `REDIS_URL` for Celery
- Ensure all environment variables are configured
- Static files served via WhiteNoise

**Local:**
- Use docker-compose for full stack
- Or run Django locally with Docker for DB/Redis

## Logging

**Configuration:** JSON or verbose format via `LOG_FORMATTER`

**Log levels:**
- DEBUG: Detailed diagnostic info
- INFO: General informational messages
- WARNING: Warning messages
- ERROR: Error messages
- CRITICAL: Critical issues

**Per-app loggers:**
- `activities`: Activity processing
- `osm`: OSM data operations
- `cost`: Cost calculations
- `core`: Core functionality
- `celery`: Task queue

## Performance Optimization

### Django Silk (Optional)
Enable profiling: `ENABLE_SILK=True` in `.env`
Access: http://localhost:8000/silk/

### Database Optimization
- Spatial indexes on geometry fields
- Select/prefetch related for foreign keys
- Database-backed caching for heavy queries

### Caching
- 15-minute cache timeout
- Cache keys: activity completeness, season stats
- Invalidation via signals

### Activity Parser Performance
- Parser profiling via ActivityParserProfile model
- Benchmarks stored for each run
- Optimize spatial queries for large datasets

## Security Notes

- Email-based authentication (no username/password)
- OAuth with Strava
- CSRF protection enabled
- Proxy SSL headers for HTTPS
- Rate limiting on Strava API tasks
- No sensitive data in logs (JSON formatter strips tokens)

## Common Issues & Solutions

### "No module named X"
- Ensure venv is activated: `source venv/bin/activate`
- Reinstall requirements: `python3 -m pip install -r requirements.txt`

### PostGIS not found
- Ensure PostGIS extension is installed: `CREATE EXTENSION postgis;`
- Use provided docker-compose setup

### Celery tasks not running
- Check Redis is running: `docker-compose ps`
- Check worker logs: `docker-compose logs worker`
- Verify `REDIS_URL` is correct

### Strava webhook not receiving events
- Ensure webhook is registered via Strava API
- Check webhook endpoint is publicly accessible
- Verify webhook secret matches configuration

### Activity processing errors
- Check OSM data is loaded for the ski area
- Verify GPS track has sufficient points
- Review activity parser logs

### Migration issues
- Ensure venv is activated before running migrations
- Use `python3` not `python`
- Check database connection is working

## Code Style & Conventions

- PEP 8 for Python code
- Black formatting (line length 120)
- Django naming conventions
- Descriptive variable names for spatial operations
- Comments for complex algorithms (especially activity parser)

## Contributing

1. Create feature branch from `main`
2. Write tests for new functionality
3. Ensure all tests pass
4. Update this documentation if needed
5. Create pull request to `main`

## Git Workflow

**Current branch:** main
**Main branch:** main (use for PRs)

**Recent commits:**
- 61f9608 - cache invalidation
- 0bf1423 - add delete button
- 3fc62f4 - add caching
- 39ee688 - improve performance
- 7be8e60 - fix: skip updating manually modified activities

## Resources

### Dependencies
- [Django 5.2 Documentation](https://docs.djangoproject.com/en/5.2/)
- [GeoDjango Tutorial](https://docs.djangoproject.com/en/5.2/ref/contrib/gis/tutorial/)
- [PostGIS Documentation](https://postgis.net/documentation/)
- [Celery Documentation](https://docs.celeryproject.org/)
- [Strava API Documentation](https://developers.strava.com/)

### Key Libraries
- **GIS:** GeoPandas, Shapely, Fiona, PyProj
- **OSM:** osmium, overpass
- **Data:** NumPy, Pandas, SciPy
- **Visualization:** Matplotlib, Pillow

## Support

For issues or questions:
1. Check logs: `docker-compose logs <service>`
2. Review Django admin error logs
3. Check Celery Flower for task failures
4. Enable Django Silk for profiling

## License

(Add license information if applicable)

---

**Last Updated:** 2025-12-25
**Django Version:** 5.2.6
**Python Version:** 3.11
**PostgreSQL Version:** 16
**PostGIS Version:** 3.4
