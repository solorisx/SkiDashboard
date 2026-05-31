# Summer Activity Tracking & Season-Pass Costing

> **Status:** Implemented · **Branch:** `claude/summer-activities-tracking-Xkp4c`
> **Implementing commit:** `d292e38` — *"Add manual summer activity tracking with season-pass costing"*
> **Audience:** Engineers working on SlopeLog. Assumes familiarity with the
> codebase, GeoDjango, django-money and the existing season-pass model.
> **Scope:** Internal technical reference. Not user-facing and not served by the
> web app (lives under `docs/`, outside `templates/`/`static/`).

---

## 1. Summary

SlopeLog historically modelled only **winter ski activities**, ingested from
Strava (`type == 'AlpineSki'`) through the GPS/lift parsing pipeline
(`activities/activity_parser.py`). This feature adds **manual tracking of
off-season ("summer") activities** — hikes, bike rides, via ferrata, etc. — and
folds their economic value into season-pass cost analysis.

Design principle: **summer activities are a separate model, not a flag on
`Activity`.** Every ski-specific view, statistic, badge rule and the trip
clustering algorithm queries `Activity`; by keeping summer data in a distinct
model they remain **winter-only by construction**, with zero risk of leaking
into lift/piste/completeness analytics. The requirement *"check all views handle
summer activities or exclude them if not applicable"* is therefore satisfied by
the data model, not by auditing dozens of querysets.

---

## 2. Data Model

Both models live in `activities/models.py` (appended after
`ActivityParserProfile`). Migrations: `activities/migrations/0026_*` (schema) and
`0027_seed_summer_activity_types.py` (built-in types).

### 2.1 `SummerActivityType`

User-selectable category for a summer activity. Built-in types are **global**
(`user IS NULL`, seeded by migration `0027`); users may add their own.

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK→`auth.User`, null | NULL ⇒ built-in global type |
| `name` | `CharField(100)` | Display name |
| `natural_key` | `SlugField(120)`, unique | Stable id (e.g. `mountain-biking`) |
| `icon` | `CharField(100)` | Bootstrap-icons class, default `bi bi-bicycle` |
| `color` | `CharField(20)` | Hex colour for UI accents |
| `sort_order` | `PositiveIntegerField` | Ordering (default 100) |
| `is_active` | `BooleanField` | Soft-disable a type |

Helper:

```python
@classmethod
def for_user(cls, user):
    """Active types available to a user: built-in globals + their own."""
    return cls.objects.filter(is_active=True).filter(Q(user__isnull=True) | Q(user=user))
```

Seeded defaults (migration `0027`): `hiking`, `trail-running`,
`mountain-biking`, `road-cycling`, `via-ferrata`, `climbing`, `swimming`,
`wellness`, `other`. The seed is idempotent (`update_or_create` on
`natural_key`) and reversible.

### 2.2 `SummerActivity`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK→`auth.User`, CASCADE | owner |
| `name` | `CharField(200)` | |
| `activity_type` | FK→`SummerActivityType`, PROTECT | required |
| `date` | `DateField` | calendar date (no GPS, so no datetime needed) |
| `timezone` | `CharField(100)`, null | IANA tz, optional |
| `strava_id` | `PositiveBigIntegerField`, null, **unique** | optional manual Strava link |
| `strava_type` | `CharField(100)`, null | raw Strava `sport_type` |
| `ski_area` | FK→`osm.SkiArea`, **SET_NULL** | optional location |
| `season_pass` | FK→`cost.SeasonPass`, **SET_NULL** | optional attribution; `related_name='summer_activities'` |
| `distance` | `FloatField`, null | **metres** (consistent with `Activity.total_distance`) |
| `elevation_gain` | `FloatField`, null | metres |
| `duration` | `DurationField`, null | |
| `cost` | `MoneyField(CHF)`, null | out-of-pocket amount paid |
| `value` | `MoneyField(CHF)`, null | ticket-equivalent value when covered |
| `notes` | `TextField`, blank | |

Indexes: `(user, -date)`, `(season_pass)`.

Cross-app FK note: the `season_pass` FK is declared as the **string**
`'cost.SeasonPass'`. `cost/models.py` imports `activities.models` at module top
(`from activities.models import Activity`), so a hard import the other way would
create a cycle. The lazy string reference avoids it; `activities.models` never
imports `cost`. Migration `0026` carries an explicit
`('cost', '0004_alter_seasonpass_price_currency_and_more')` dependency so the
`cost_seasonpass` table exists before the FK is added. The migration graph stays
acyclic because the `cost` app depends only on `osm`/`auth`, never on
`activities`.

Properties: `is_covered` (`season_pass_id is not None`) and `get_strava_url()`.

---

## 3. Season-Pass Costing

All costing logic is on `cost.SeasonPass` (`cost/models.py`). The existing
`get_valid_activities()` / `count_valid_activities()` continue to count **winter
ski `Activity` rows** matched spatially+temporally to the pass — unchanged and
unaffected by summer data.

### 3.1 New aggregates

```python
def get_summer_activities(self):
    from activities.models import SummerActivity
    return SummerActivity.objects.filter(season_pass=self)

@property
def total_summer_value(self):
    # summed in Python to skip NULLs; assumes pass currency (mixed currency raises)
    ...

@property
def summer_avg_value(self):
    # total summer value / number of summer activities
    ...
```

### 3.2 Redefined cost-per-day

The spec defines two averages:

* **Summer average cost** = average *value* of summer activities
  → `SeasonPass.summer_avg_value`.
* **Winter cost per day** = `(pass price − total summer value) / number of winter activities`
  → `SeasonPass.cost_per_day` (redefined):

```python
@property
def cost_per_day(self):
    count = self.count_valid_activities()       # winter ski activities
    if count <= 0:
        return None
    net_price = self.price
    summer_value = self.total_summer_value
    if summer_value is not None:
        net_price = self.price - summer_value
    return round(net_price / count, 2)
```

Rationale: a season pass's price is partly "consumed" by off-season use. Summer
value is deducted from the pass price before attributing the remainder across
winter ski days, so heavy summer use lowers the cost booked against skiing.

`cost_per_day` keeps its name/return type (`Money`) for backward compatibility
with templates and `home_stats`; behaviour now nets out summer value.

### 3.3 Worked example (mirrors `SeasonPassSummerCostingTests`)

Pass price CHF 600, 3 winter ski activities, 2 summer activities worth CHF 50 each:

| Metric | Value |
|--------|-------|
| `total_summer_value` | CHF 100 |
| `summer_avg_value` | CHF 50 |
| `cost_per_day` (winter) | (600 − 100) / 3 = **CHF 166.67** |
| without summer activities | 600 / 3 = CHF 200.00 |

---

## 4. Integration Points

| Location | Change |
|----------|--------|
| `activities/views/summer.py` | New CRUD views (list+filters, create, edit, delete), all `@login_required`, owner-scoped |
| `activities/forms.py` → `SummerActivityForm` | `ModelForm`; exposes distance in **km** / duration in **minutes** and converts to m/`timedelta` in `save()`; limits `activity_type` to `for_user()` and `season_pass` to the user's passes; ski-area picker via DAL `ModelSelect2` autocomplete |
| `activities/urls.py` | `summer/`, `summer/new/`, `summer/<pk>/edit/`, `summer/<pk>/delete/` |
| `activities/views/__init__.py` | Re-exports the four views |
| `cost/views.py` → `season_pass_detail` | Adds summer list, `total_summer_value`, `summer_avg_value`; `cost_per_day` now from the model property |
| `activities/views/api.py` → `home_stats` | Per-pass and aggregate `avg_cost_per_day` net out `total_summer_value` |
| `core/templates/activities/summer_activity_*.html` | List / form / delete-confirm templates |
| `core/templates/cost/season_pass_detail.html` | "Summer value" stat card, "Winter cost / day" relabel, summer activities table |
| `core/templates/base/sidebar.html` | "Summer" nav entry under *Activities*; `All Activities` active-state guard excludes `/activities/summer` |
| `activities/admin.py` | `SummerActivityTypeAdmin`, `SummerActivityAdmin` (raw-id FKs) |

The summer form page relies on `base.html` auto-loading `{{ form.media }}` (it
renders that block whenever a `form` is in context), which pulls the DAL/select2
assets for the ski-area autocomplete; jQuery + select2 are already global.

### Views deliberately left unchanged

`activity_list`, `*_insights`, `statistics`, `trips`, badge assignment
(`badges.py`), trip clustering (`trips.py`) and the base query
`get_user_activities_base_query()` all operate on `Activity` and so never see
summer rows. This is intentional and is the core of the "exclude where not
applicable" requirement.

---

## 5. Strava Linkage

"Optional link to Strava" is a **manual association**, not an import. The
ingest pipeline (`activities/tasks.py`, `batch.py`, `activity_parser.py`) still
filters to `AlpineSki` and is untouched. A user may paste a Strava activity ID
(and optionally its sport type) into the form; `strava_id` is unique and
`get_strava_url()` renders a deep link. Automated summer-activity import from
Strava is explicitly **out of scope** for this change.

---

## 6. Testing

`activities/tests/test_summer_activities.py`:

* `SummerActivityModelTests` — defaults, `get_strava_url`, `for_user` scoping.
* `SeasonPassSummerCostingTests` — the costing formula, summer aggregates, and
  proof that summer rows do **not** alter `count_valid_activities()` /
  `Activity` counts.
* `SummerActivityViewTests` — login gating, list/type-filter, create (km→m,
  min→timedelta conversion), delete, and cross-user 404 isolation.

Run (PostGIS required):

```bash
python3 manage.py test activities.tests.test_summer_activities --keepdb
```

---

## 7. Known Limitations / Future Work

* **Currency:** `total_summer_value` sums in Python and assumes summer values
  share the pass currency; mixed currencies raise (intentional loud failure).
  Multi-currency normalisation is future work.
* **Premium gating:** summer tracking is available to all authenticated users;
  season-pass management remains `@premium_required`. Revisit if summer tracking
  should be premium-only.
* **No GPS/geometry:** summer activities are metadata-only; no map rendering.
* **Trips:** summer activities are not clustered into `Trip`s (trips are a
  ski-season concept).
