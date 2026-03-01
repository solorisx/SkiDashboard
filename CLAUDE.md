# SlopeLog — Claude Development Guide

## Project Overview

SlopeLog is a Django GIS web application that tracks ski activities, analyzes GPS tracks to detect lift rides and piste runs, and provides comprehensive statistics and insights. The application integrates with Strava for activity syncing and uses OpenStreetMap data for ski infrastructure mapping.

**Key Technologies:**
- Django 5.2.6 with GeoDjango
- PostgreSQL 16 with PostGIS 3.4
- Celery 5.5.1 + Redis 7 for async tasks
- Python 3.11
- Docker & Docker Compose

---

## Quick Start

### Prerequisites
- Docker and Docker Compose installed
- Python 3.11 (for local development outside Docker)

### Docker Development Setup (Recommended)

```bash
# 1. Copy and fill in environment variables
cp .env.example .env   # or create .env manually

# 2. Start all services
docker compose up -d

# 3. Apply migrations (auto-applied via start.sh in production)
docker compose exec web python3 manage.py migrate
```

Services started by `docker compose`:
| Service  | Purpose                     | Port  |
|----------|-----------------------------|-------|
| `web`    | Django (gunicorn via start.sh) | 8000  |
| `worker` | Celery worker               | —     |
| `beat`   | Celery beat scheduler       | —     |
| `flower` | Celery monitoring UI        | 5555  |
| `db`     | PostGIS 16-3.4              | 55432 |
| `redis`  | Message broker / cache      | 56379 |

Note: The `db` port on the host is **55432** (not 5432) to avoid conflicts.

### Local Development (Outside Docker)

**CRITICAL: Always use `python3`, never `python`.**

```bash
# Activate virtual environment first
source venv/bin/activate

# Install dependencies
python3 -m pip install -r requirements.txt

# Apply migrations
python3 manage.py migrate

# Run dev server
python3 manage.py runserver

# Run Celery worker (separate terminal, venv activated)
celery -A activities worker -l info

# Run Celery beat (separate terminal, venv activated)
celery -A activities beat -l info
```

---

## Project Structure

```
SkiDashboard/
├── core/                        # User management, auth, Django settings
│   ├── models.py               # UserProfile
│   ├── settings.py             # Django configuration
│   ├── strava_adapter.py       # Custom Strava OAuth adapter
│   ├── account_adapter.py      # Async email adapter
│   ├── signals.py              # User signup signals
│   └── tasks.py                # Core Celery tasks
│
├── activities/                  # Strava integration & GPS analysis
│   ├── models.py               # Activity, Lap, Record, LiftRide, PisteRide,
│   │                           #   Badge, ActivityBadge, Trip, StravaSyncSettings,
│   │                           #   ActivityParserProfile, ActivityPisteSegment
│   ├── activity_parser.py      # GPS track analysis (~1700 lines)
│   ├── segment_matcher.py      # Piste segment matching logic
│   ├── strava_interface.py     # Strava API client
│   ├── batch.py                # Batch activity processing
│   ├── badges.py               # Badge assignment logic
│   ├── trips.py                # Trip clustering algorithm
│   ├── celery.py               # Celery app definition (app name: 'activities')
│   ├── signals.py              # Cache invalidation signals
│   ├── tasks.py                # Async Strava sync tasks
│   ├── forms.py
│   ├── services/
│   │   ├── statistics.py       # Statistics services
│   │   └── strava.py           # Strava service helpers
│   ├── utils/
│   │   ├── completeness.py     # Ski area completeness calculations
│   │   ├── data_processing.py  # Data transformation utilities
│   │   ├── image_generator.py  # Share image generation (Pillow/Matplotlib)
│   │   ├── queries.py          # Reusable ORM query helpers
│   │   └── seasons.py          # Season boundary management
│   ├── views/
│   │   ├── activity.py         # Activity list, detail, map
│   │   ├── admin_profiling.py  # Parser profiling dashboard
│   │   ├── api.py              # JSON API endpoints (lift/piste/season-pass CRUD)
│   │   ├── insights.py         # Activity statistics/insights
│   │   ├── lift_insights.py    # Lift-specific analytics
│   │   ├── piste_insights.py   # Piste-specific analytics
│   │   ├── statistics.py       # Statistics views
│   │   ├── sync.py             # Strava sync views
│   │   ├── trips.py            # Trip list, detail, rename, recluster
│   │   └── webhook.py          # Strava webhook handler
│   ├── urls.py
│   ├── trips_urls.py
│   └── tests/
│       ├── test_activity_parser.py
│       └── test_performance_real_data.py
│
├── osm/                         # OpenStreetMap integration
│   ├── models.py               # Node, Way, WayNode, Station, Aerialway, Piste,
│   │                           #   PisteSegment, SkiArea, SkiAreaBoundary,
│   │                           #   SkiAreaNetwork, SkiAreaNetworkMember,
│   │                           #   LiftFilterConfig
│   ├── osm_parser.py           # OSM file parsing via osmium (~640 lines)
│   ├── osm_downloader.py       # Overpass API client
│   ├── osm_interface.py        # OSM data loading helpers
│   ├── osm_segments.py         # Piste segment generation
│   ├── osm_util.py             # OSM utility functions
│   ├── piste_polygon.py        # Piste polygon/area handling
│   ├── tasks.py                # OSM processing async tasks
│   ├── urls.py
│   └── views.py
│
├── cost/                        # Season pass & ticket price tracking
│   ├── models.py               # TicketPrice, SeasonPass
│   ├── prices.py               # Price calculation helpers
│   ├── seasonpass.py           # Season pass validation logic
│   ├── urls.py
│   └── views.py
│
├── static/                      # Custom CSS, JS, images
├── staticfiles/                 # Collected static files (WhiteNoise)
├── locale/                      # i18n translation files
├── sql/                         # Raw SQL scripts
├── docker-compose.yaml
├── Dockerfile
├── requirements.txt
├── manage.py
└── start.sh                     # Entrypoint: runs migrations then gunicorn
```

---

## Database Models

### Core App
- **UserProfile** — User preferences: language, timezone, units, excluded lift types, season boundaries

### Activities App
- **Trip** — Groups of consecutive activities (auto-clustered). Has `name`, `auto_name`, `name_modified` flag, `start_date`, `end_date`
- **Activity** — Main activity record: GPS data, Strava integration, `ski_area` FK, `trip` FK, `timezone`, `manually_modified`, cost/value money fields
- **Lap** — Activity segments with `geom` LineString field
- **Record** — Individual GPS points (PostGIS PointField)
- **LiftRide** — `Lap` → `Aerialway` with `uphill` and `timestamp`
- **PisteRide** — `Lap` → `Piste` with `timestamp`
- **ActivityPisteSegment** — `Activity` → `PisteSegment` many-to-many
- **Badge** — Achievement definitions with `natural_key`, `rarity` (bronze/silver/gold/platinum/legendary), `sort_key`
- **ActivityBadge** — User badge assignments per activity
- **StravaSyncSettings** — Singleton-ish row: scheduled sync toggle, interval, webhook toggle, webhook secrets
- **ActivityParserProfile** — Per-activity performance profiling data

### OSM App
- **Node** — OSM nodes (base spatial entity, `osm_id`, `geom` PointField, `tags`)
- **Way** — OSM ways, nodes via `WayNode` through-model ordered by `sequence`
- **WayNode** — Ordered node membership in a way
- **Station** — Lift stations (OneToOne with Node)
- **Aerialway** — Ski lifts: `aerialway` type, capacity, duration, heating, `bottom_station`, `top_station`, `station_nodes` M2M
- **Piste** — Ski runs: difficulty, grooming, type, `lit`, `oneway`, `length` (auto-computed in EPSG:3857), `segments_generated`
- **PisteSegment** — Piste sub-segments for fine-grained tracking; shared across pistes
- **SkiArea** — Ski resort: `osm_id`, `geom` MultiPolygon, `ways` M2M, `country` (CountryField), price fields
- **SkiAreaBoundary** — Alternative boundary representation (abstract base `AbstractSkiArea`)
- **SkiAreaNetwork** — Ski pass network (e.g. Epic Pass): name, `season_pass_price`
- **SkiAreaNetworkMember** — SkiArea membership in a network with `valid_from`, `valid_to`, `max_days`, `valid_during`
- **LiftFilterConfig** — Not a DB model; a config class that manages global + per-user aerialway type exclusions

### Cost App
- **TicketPrice** — Day/season pass pricing per ski area and date range
- **SeasonPass** — User season pass: covers a `SkiArea` OR a `SkiAreaNetwork`. Includes `cost_per_day` property

---

## Key URL Routes

### Activities
| URL Pattern                                  | View                    |
|----------------------------------------------|-------------------------|
| `/activities/`                               | Activity list           |
| `/activities/<id>/`                          | Activity detail         |
| `/activities/<id>/map/`                      | Map view                |
| `/activities/<id>/reprocess/`               | Reprocess               |
| `/activities/insights/`                      | Insights dashboard      |
| `/activities/lift-insights/`                 | Lift analytics          |
| `/activities/piste-insights/`               | Piste analytics         |
| `/activities/admin/profiling/`              | Profiling dashboard     |
| `/activities/strava/webhook/`               | Strava webhook          |
| `/activities/sync_strava/`                  | Manual sync             |

### Trips
| URL Pattern               | View                                |
|---------------------------|-------------------------------------|
| `/trips/`                 | Trip list                           |
| `/trips/<id>/`            | Trip detail                         |
| `/trips/<id>/rename/`     | Rename trip (JSON POST)             |
| `/trips/recluster/`       | Re-cluster all activities (POST)    |

### API (JSON)
- `GET/POST/PATCH/DELETE /api/lift-ride/` — Lift ride CRUD
- `DELETE /api/piste-ride/<id>/` — Delete piste ride
- `GET/POST/PATCH/DELETE /api/season-pass/` — Season pass management
- `GET /api/season-stats/` — Season statistics
- `POST /api/activity/<id>/` — Update activity
- `POST /api/update-strava-description/<id>/` — Update Strava description

### OSM Admin
- `POST /osm/admin/sync-osm-api/` — Sync from Overpass API
- `POST /osm/admin/sync-osm-file/` — Sync from OSM file
- `GET /osm/skiarea-autocomplete/` — Ski area autocomplete

---

## Architecture & Key Features

### GIS-First Design
- All spatial operations use PostGIS with WGS84 (SRID 4326) for storage
- Use `Transform(3857)` when doing metric distance calculations (e.g. piste length)
- Spatial indexes on Activity, Aerialway, Piste models
- Distance and intersection queries for matching GPS tracks to infrastructure
- `Piste.length` is auto-calculated in EPSG:3857 on save

### Activity Processing Pipeline
1. **Strava API** → Import via webhook (`StravaSyncSettings`) or scheduled sync
2. **GPS track analysis** → Lap detection, turning points (`activity_parser.py`)
3. **Spatial matching** → Identify lifts/pistes via PostGIS intersection
4. **Segment matching** → Fine-grained piste tracking (`segment_matcher.py`)
5. **Cost calculation** → Season pass value analysis (`cost/seasonpass.py`)
6. **Badge assignment** → Achievement tracking (`badges.py`)
7. **Trip clustering** → Group activities into trips (`trips.py`)

### Trips Feature
Activities are automatically grouped into trips by `cluster_activities_into_trips()`:
- Two activities belong to the same trip if there is at most **one idle day** between them (gap ≤ 2 days)
- Trip names are auto-generated from ski area names and date range
- User-modified names (`name_modified=True`) are preserved through re-clustering
- Trips are re-clustered automatically after Strava sync

### Lift Ride Detection Algorithm
Located in `activities/activity_parser.py`:
- Graph-based turning point detection
- Spatial matching to known lift infrastructure (Aerialway geometries)
- Speed and altitude-based filtering
- Multi-lift route analysis using Dijkstra's algorithm
- Station network matching
- `apply_exceptions()` handles known OSM data quirks

### Lift Type Filtering (`LiftFilterConfig`)
In `osm/models.py`:
- `GLOBAL_EXCLUDED_LIFT_TYPES` — Always excluded (explosive, goods, zip_line, construction, disused, etc.)
- `DEFAULT_EXCLUDED_LIFT_TYPES` — Excluded by default but overridable per user (magic_carpet, rope_tow)
- Users can customize via `UserProfile.excluded_lift_types`
- Use `LiftFilterConfig.filter_lifts_queryset(queryset, user)` to filter aerialways

### Automatic Station Creation
During OSM parsing, if an aerialway way has no associated station nodes, stations are automatically created from the way's endpoint nodes. This handles missing OSM data gracefully.

### Strava Integration
- OAuth via django-allauth (Strava social provider)
- Automatic token refresh
- Webhook-based real-time sync (controlled by `StravaSyncSettings`)
- Scheduled sync via Celery beat
- Two-way sync: can update Strava activity descriptions
- Webhook verify token + HMAC signing secret in `StravaSyncSettings`

### Caching Strategy
- Database-backed cache with 15-minute timeout
- Per-activity completeness caching
- Per-ski-area statistics caching
- Signal-based invalidation on activity changes (`activities/signals.py`)

### Badge System
- Rarity levels: bronze, silver, gold, platinum, legendary
- `natural_key` for stable identification across deployments
- `sort_key` for display ordering
- Categories: lift-based, elevation, exploration, ski area completeness

---

## Common Development Tasks

### Database Migrations

**Always activate venv first when running outside Docker!**

```bash
source venv/bin/activate
python3 manage.py makemigrations
python3 manage.py migrate
```

### Reprocess Activities

```bash
python3 manage.py reprocess --all     # Reprocess all activities
python3 manage.py reprocess <id>      # Reprocess specific activity
```

### Download OSM Data

```bash
python3 manage.py download_osm <ski_area_id>
```

### Update Piste Segments

```bash
python3 manage.py update_segments
```

### Run Performance Benchmarks

```bash
python3 manage.py performance_benchmark
```

### Test Strava Integration

```bash
python3 manage.py test_strava              # Test connection
python3 manage.py test_strava print        # List activities
python3 manage.py test_strava <id>         # Test specific activity parsing
```

### Run Tests

```bash
python3 manage.py test                     # All tests
python3 manage.py test activities          # App-specific
python3 manage.py test --keepdb           # Preserve OSM data between runs (recommended)
python3 manage.py test --parallel         # Parallel execution
```

### Collect Static Files

```bash
python3 manage.py collectstatic --noinput
```

### Access Django Shell

```bash
python3 manage.py shell
```

---

## Configuration

### Environment Variables

**Note:** Environment variable names in `settings.py`:
- `DJANGO_SECRET_KEY` (not `SECRET_KEY`)
- `DJANGO_DEBUG` (not `DEBUG`)

**Database:**
- `DATABASE_URL` — PostgreSQL+PostGIS connection string

**Redis:**
- `REDIS_URL` — Celery broker and Django cache backend

**Django:**
- `DJANGO_SECRET_KEY` — Django secret key
- `DJANGO_DEBUG` — `True` or `False`
- `ALLOWED_HOSTS` — Comma-separated allowed hosts
- `CSRF_TRUSTED_ORIGINS` — Comma-separated trusted origins

**Strava:**
- `STRAVA_CLIENT_ID`
- `STRAVA_CLIENT_SECRET`

**Email (Mailgun):**
- `MAILGUN_API_KEY`
- `MAILGUN_SENDER_DOMAIN`
- `DEFAULT_FROM_EMAIL`

**Email (SMTP fallback):**
- `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`

**Optional:**
- `ENABLE_SILK` — `true` to enable Django Silk profiling
- `LOG_LEVEL` — `DEBUG`, `INFO`, `WARNING`, `ERROR`
- `LOG_FORMATTER` — `verbose` or `json`

### Celery

- **App module:** `activities` (defined in `activities/celery.py`)
- **Broker:** Redis (`REDIS_URL`)
- **Scheduled Tasks (Beat):** Strava sync (configurable interval from `StravaSyncSettings`), badge recalculation, cache cleanup

**Command reference:**
```bash
celery -A activities worker -l info    # Worker
celery -A activities beat -l info      # Scheduler
celery -A activities flower --port=5555  # Monitoring UI
```

### Database

PostGIS is required. The app auto-detects cloud databases and adjusts settings.

```
postgresql://user:password@host:port/dbname
```

Local default (from docker-compose): `postgresql://django:password@localhost:55432/postgres`

---

## Testing

- Tests live in `*/tests/` directories
- Activity parser has a comprehensive unit test suite
- Performance tests use real OSM data — use `--keepdb` to preserve it between runs
- Use `test_performance_real_data.py` to benchmark against realistic datasets

---

## Deployment

### Docker (Production)

```bash
docker build -t skidashboard .
docker compose up -d
```

Migrations run automatically via `start.sh` before gunicorn starts.

### Cloud Platforms (Render, Railway, etc.)

- Set `DATABASE_URL` with PostGIS-enabled database
- Set `REDIS_URL` for Celery
- Static files served via WhiteNoise (no separate static server needed)

---

## Logging

**Configuration:** `LOG_FORMATTER=json` or `LOG_FORMATTER=verbose`

Per-app loggers: `activities`, `osm`, `cost`, `core`, `celery`

Check Docker service logs:
```bash
docker compose logs web
docker compose logs worker
docker compose logs beat
```

---

## Performance Optimization

### Django Silk (Optional Profiling)

```bash
ENABLE_SILK=True  # in .env
# Access at: http://localhost:8000/silk/
```

### Database

- Spatial indexes on geometry fields (handled by migrations)
- `select_related` / `prefetch_related` on foreign keys in list views
- Database-backed caching for heavy queries (15-minute timeout)
- Lift graph building is expensive — cached in parser instances

### Activity Parser Performance

- `ActivityParserProfile` stores per-operation timing per activity
- Profiling dashboard at `/activities/admin/profiling/`
- Run `python3 manage.py performance_benchmark` for comprehensive benchmarks

---

## Security

- Email-based authentication (no username/password login)
- OAuth with Strava (django-allauth)
- CSRF protection enabled
- Proxy SSL headers for HTTPS
- Rate limiting on Strava API tasks: `@shared_task(rate_limit='10/m')`
- Webhook HMAC signature verification via `StravaSyncSettings.webhook_signing_secret`
- Sensitive data (tokens) stripped from logs

---

## Common Issues & Solutions

| Problem | Solution |
|---------|----------|
| `No module named X` | Activate venv: `source venv/bin/activate` |
| PostGIS not found | `CREATE EXTENSION postgis;` or use docker-compose `db` |
| Celery tasks not running | Check Redis: `docker compose ps`; check `docker compose logs worker` |
| Strava webhook not receiving | Check webhook is registered; endpoint publicly accessible; verify secret |
| Activity processing errors | Check OSM data loaded for ski area; check GPS track has enough points |
| Migration issues | Activate venv; use `python3` not `python`; check DB connection |

---

## Code Style & Conventions

- **Python:** PEP 8, Black formatting (line length 120)
- **Django naming conventions** throughout
- Descriptive variable names for spatial operations
- Comments in complex algorithms (especially `activity_parser.py`)
- Money fields use `djmoney.MoneyField` with CHF as default currency
- Activities link to `SkiArea` via spatial intersection (not a direct FK during import)
- Season pass can cover either a `SkiArea` OR a `SkiAreaNetwork`, not both (enforced in `clean()`)

---

## Git Workflow

**Main branch:** `main`

1. Create feature branch from `main`
2. Write tests for new functionality
3. Ensure all tests pass
4. Update this documentation if needed
5. Create pull request to `main`

---

## Resources

### Documentation
- [Django 5.2 Documentation](https://docs.djangoproject.com/en/5.2/)
- [GeoDjango Tutorial](https://docs.djangoproject.com/en/5.2/ref/contrib/gis/tutorial/)
- [PostGIS Documentation](https://postgis.net/documentation/)
- [Celery Documentation](https://docs.celeryproject.org/)
- [Strava API Documentation](https://developers.strava.com/)

### Key Libraries
- **GIS:** GeoPandas 1.0.1, Shapely 2.0.7, PyProj 3.7.1, pyogrio 0.10.0
- **OSM:** osmium 3.7.0, overpass 0.7.2, overpy 0.7, osm2geojson 0.2.5
- **Data:** NumPy 2.2.3, Pandas 2.2.3, SciPy 1.15.2
- **Visualization:** Matplotlib 3.9.4, Pillow 11.0.0
- **Auth/HTTP:** stravalib 2.2, django-allauth 65.4.1, requests-oauthlib 2.0.0
- **Misc:** django-money 3.5.3, django-countries 7.6.1, humanize 4.12.2, babel 2.17.0

---

**Last Updated:** 2026-03-01
**Django Version:** 5.2.6
**Python Version:** 3.11
**PostgreSQL Version:** 16
**PostGIS Version:** 3.4
