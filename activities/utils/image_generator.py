"""
Utility for generating shareable activity images with stats and mini map.
"""

import io
import logging
from datetime import timedelta
from PIL import Image, ImageDraw, ImageFont
import matplotlib

matplotlib.use("Agg")  # Use non-interactive backend
import matplotlib.pyplot as plt
from django.contrib.gis.geos import LineString

logger = logging.getLogger(__name__)

# Image dimensions for Instagram story format
IMAGE_WIDTH = 1080
IMAGE_HEIGHT = 1920

# Activity share color scheme
COLOR_BG = "#1a1a2e"  # Dark blue background
COLOR_TEXT_PRIMARY = "#ffffff"
COLOR_TEXT_SECONDARY = "#a0a0b0"
COLOR_ACCENT = "#0d6efd"  # Bootstrap primary blue
COLOR_SUCCESS = "#198754"
COLOR_WARNING = "#ffc107"
COLOR_CARD_BG = "#2a2a3e"

# Season share color scheme (premium, darker palette)
COLOR_SEASON_BG = "#0f172a"  # Very deep navy
COLOR_SEASON_CARD = "#1a2644"  # Card background
COLOR_SEASON_CARD_ALT = "#1e2d52"  # Alternate card
COLOR_SEASON_ACCENT = "#38bdf8"  # Sky blue
COLOR_SEASON_GOLD = "#f59e0b"  # Amber/gold for highlights
COLOR_SEASON_DIVIDER = "#1e3055"  # Subtle divider lines

# Badge rarity colors (shared)
RARITY_COLORS = {
    "legendary": "#9333ea",
    "platinum": "#cbd5e1",
    "gold": "#f59e0b",
    "silver": "#94a3b8",
    "bronze": "#b45309",
}


def get_font(size, bold=False):
    """
    Get a font object. Falls back to default if custom fonts not available.
    """
    try:
        if bold:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except Exception:
        # Fallback to default font
        return ImageFont.load_default()


def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def generate_activity_map(activity, size=(600, 600)):
    """
    Generate a mini map showing the activity track.

    Args:
        activity: Activity model instance with geom field
        size: Tuple of (width, height) for the map

    Returns:
        PIL Image object containing the map
    """
    try:
        # Extract coordinates from LineString geometry
        if not activity.geom or not isinstance(activity.geom, LineString):
            logger.warning(f"No valid geometry for activity {activity.id}")
            return _create_placeholder_map(size)

        coords = list(activity.geom.coords)
        if len(coords) < 2:
            logger.warning(f"Insufficient coordinates for activity {activity.id}")
            return _create_placeholder_map(size)

        # Separate x (longitude) and y (latitude)
        lons = [coord[0] for coord in coords]
        lats = [coord[1] for coord in coords]

        # Create figure with tight layout to fill the entire space
        fig, ax = plt.subplots(figsize=(size[0] / 100, size[1] / 100), dpi=100)
        fig.patch.set_facecolor(COLOR_CARD_BG)
        ax.set_facecolor(COLOR_BG)

        # Remove all margins and padding
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

        # Plot the track
        ax.plot(lons, lats, color=COLOR_ACCENT, linewidth=3, alpha=0.9, solid_capstyle="round", solid_joinstyle="round")

        # Add start point marker (green)
        ax.plot(
            lons[0],
            lats[0],
            "o",
            color=COLOR_SUCCESS,
            markersize=12,
            markeredgewidth=2,
            markeredgecolor="white",
            zorder=5,
        )

        # Add end point marker (red)
        ax.plot(
            lons[-1],
            lats[-1],
            "s",
            color="#dc3545",
            markersize=12,
            markeredgewidth=2,
            markeredgecolor="white",
            zorder=5,
        )

        # Remove axes
        ax.set_xticks([])
        ax.set_yticks([])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_visible(False)
        ax.spines["left"].set_visible(False)

        # Add some padding
        x_range = max(lons) - min(lons)
        y_range = max(lats) - min(lats)
        padding = 0.1  # 10% padding
        ax.set_xlim(min(lons) - x_range * padding, max(lons) + x_range * padding)
        ax.set_ylim(min(lats) - y_range * padding, max(lats) + y_range * padding)

        # Set aspect ratio to 'auto' to fill the entire rectangle
        ax.set_aspect("auto")

        # Convert matplotlib figure to PIL Image
        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches=None, pad_inches=0, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)
        buf.seek(0)

        return Image.open(buf)

    except Exception as e:
        logger.error(f"Error generating map for activity {activity.id}: {e}")
        return _create_placeholder_map(size)


def _create_placeholder_map(size):
    """Create a placeholder map image when actual map cannot be generated."""
    img = Image.new("RGB", size, color=hex_to_rgb(COLOR_CARD_BG))
    draw = ImageDraw.Draw(img)

    # Draw a simple placeholder
    center_x, center_y = size[0] // 2, size[1] // 2
    draw.text(
        (center_x, center_y), "Map Unavailable", fill=hex_to_rgb(COLOR_TEXT_SECONDARY), anchor="mm", font=get_font(24)
    )

    return img


def format_duration(duration):
    """Format duration (timedelta or seconds) to HH:MM:SS or MM:SS format."""
    if not duration:
        return "00:00"

    # Handle timedelta objects
    if isinstance(duration, timedelta):
        total_seconds = int(duration.total_seconds())
    else:
        # Assume it's already in seconds
        total_seconds = int(duration)

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def create_shareable_image(activity):
    """
    Create a shareable Instagram story-sized image (1080x1920px) with activity details.

    Args:
        activity: Activity model instance

    Returns:
        PIL Image object (1080x1920px PNG)
    """
    # Create base image
    img = Image.new("RGB", (IMAGE_WIDTH, IMAGE_HEIGHT), color=hex_to_rgb(COLOR_BG))
    draw = ImageDraw.Draw(img)

    # Fonts
    font_title = get_font(60, bold=True)
    font_heading = get_font(40, bold=True)
    font_stat_value = get_font(70, bold=True)
    font_stat_label = get_font(32)
    font_small = get_font(28)
    font_branding = get_font(36)

    # --- HEADER SECTION ---
    y_offset = 60

    # Activity name
    activity_name = activity.name or "Ski Activity"
    # Wrap text if too long
    if len(activity_name) > 25:
        activity_name = activity_name[:22] + "..."

    draw.text(
        (IMAGE_WIDTH // 2, y_offset), activity_name, fill=hex_to_rgb(COLOR_TEXT_PRIMARY), anchor="mt", font=font_title
    )
    y_offset += 100

    # Ski area badge
    ski_area_name = activity.ski_area.name if activity.ski_area else "Unknown Area"
    if len(ski_area_name) > 30:
        ski_area_name = ski_area_name[:27] + "..."

    # Draw rounded rectangle for ski area badge
    badge_height = 50
    badge_padding = 20
    text_bbox = draw.textbbox((0, 0), ski_area_name, font=font_small)
    text_width = text_bbox[2] - text_bbox[0]
    badge_width = text_width + badge_padding * 2
    badge_x = (IMAGE_WIDTH - badge_width) // 2
    badge_y = y_offset

    draw.rounded_rectangle(
        [(badge_x, badge_y), (badge_x + badge_width, badge_y + badge_height)], radius=25, fill=hex_to_rgb(COLOR_ACCENT)
    )
    draw.text(
        (IMAGE_WIDTH // 2, badge_y + badge_height // 2),
        ski_area_name,
        fill=hex_to_rgb(COLOR_TEXT_PRIMARY),
        anchor="mm",
        font=font_small,
    )
    y_offset += badge_height + 40

    # Date
    from django.utils import timezone
    import pytz

    # Convert to activity timezone for display
    activity_tz = pytz.timezone(activity.timezone) if activity.timezone else timezone.get_current_timezone()
    local_time = activity.start_time.astimezone(activity_tz)
    date_str = local_time.strftime("%B %d, %Y")

    draw.text(
        (IMAGE_WIDTH // 2, y_offset), date_str, fill=hex_to_rgb(COLOR_TEXT_SECONDARY), anchor="mt", font=font_small
    )
    y_offset += 80

    # --- MINI MAP SECTION ---
    map_size = 500  # Reduced from 600 to 500
    map_img = generate_activity_map(activity, size=(map_size, map_size))
    map_x = (IMAGE_WIDTH - map_size) // 2
    map_y = y_offset

    # Add border around map
    border_width = 4
    draw.rounded_rectangle(
        [
            (map_x - border_width, map_y - border_width),
            (map_x + map_size + border_width, map_y + map_size + border_width),
        ],
        radius=20,
        fill=hex_to_rgb(COLOR_CARD_BG),
    )

    img.paste(map_img, (map_x, map_y))
    y_offset += map_size + 50  # Reduced spacing from 60 to 50

    # --- STATISTICS SECTION ---
    # Calculate stats
    distance_km = round(activity.total_distance / 1000, 1) if activity.total_distance else 0
    descent_m = round(activity.total_descent) if activity.total_descent else 0
    num_lifts = activity.num_lift_rides if activity.num_lift_rides else 0
    duration = format_duration(activity.total_elapsed_time)

    # Calculate completeness stats
    from activities.utils.completeness import calculate_activity_completeness, calculate_activity_piste_completeness

    lift_completeness = calculate_activity_completeness(activity)
    piste_completeness = calculate_activity_piste_completeness(activity)

    lifts_used = lift_completeness.get("lifts_used_today", 0)
    total_lifts = lift_completeness.get("total_lifts_available", 0)

    distance_skied_km = int(round(piste_completeness.get("distance_skied_today", 0) / 1000))
    total_distance_km = int(round(piste_completeness.get("total_distance_available", 0) / 1000))

    # Create stats grid (3x2)
    stats = [
        ("Distance", f"{distance_km} km", COLOR_ACCENT),
        ("Descent", f"{descent_m} m", COLOR_SUCCESS),
        ("Lifts", f"{num_lifts}", COLOR_WARNING),
        ("Duration", duration, "#17a2b8"),  # Info color
        ("Lifts", f"{lifts_used}/{total_lifts}", "#6f42c1"),  # Purple
        ("Pistes", f"{distance_skied_km}/{total_distance_km}km", "#d63384"),  # Pink
    ]

    # Grid layout
    grid_padding = 40
    card_width = (IMAGE_WIDTH - grid_padding * 3) // 2
    card_height = 170

    for idx, (label, value, color) in enumerate(stats):
        row = idx // 2
        col = idx % 2

        card_x = grid_padding + col * (card_width + grid_padding)
        card_y = y_offset + row * (card_height + 20)

        # Draw card background
        draw.rounded_rectangle(
            [(card_x, card_y), (card_x + card_width, card_y + card_height)], radius=15, fill=hex_to_rgb(COLOR_CARD_BG)
        )

        # Use smaller font for completeness stats (last 2 rows) which have more text
        # value_font = font_heading if idx >= 4 else font_stat_value
        value_font = font_stat_value

        # Draw value
        draw.text((card_x + card_width // 2, card_y + 60), value, fill=hex_to_rgb(color), anchor="mt", font=value_font)

        # Draw label
        draw.text(
            (card_x + card_width // 2, card_y + 140),
            label,
            fill=hex_to_rgb(COLOR_TEXT_SECONDARY),
            anchor="mt",
            font=font_stat_label,
        )

    y_offset += 3 * (card_height + 20) + 40  # Reduced from 60 to 40

    # --- TOP LIFTS & PISTES SECTION (TWO COLUMNS) ---
    from collections import Counter
    from activities.models import PisteRide

    # Get lift rides for this activity
    lift_counts = Counter()
    for lap in activity.laps.all():
        for lift_ride in lap.liftride_set.select_related("aerialway").all():
            if lift_ride.aerialway:
                lift_name = lift_ride.aerialway.name or f"Lift {lift_ride.aerialway.id}"
                lift_counts[lift_name] += 1

    # Get piste rides for this activity (>500m only)
    piste_rides = (
        PisteRide.objects.filter(lap__activity=activity)
        .select_related("piste", "piste__way", "lap")
        .order_by("lap__lap_index", "timestamp")
    )

    logger.info(f"Found {piste_rides.count()} total piste rides for activity {activity.id}")

    # Calculate length in meters and filter to >500m
    # Track (lap_id, piste_id) to count each piste only once per lap
    seen_lap_piste = set()
    piste_counts = Counter()

    for piste_ride in piste_rides:
        if piste_ride.piste.geom:
            geom_meters = piste_ride.piste.geom.transform(3857, clone=True)
            length_meters = int(geom_meters.length)
            logger.debug(f"Piste {piste_ride.piste.name or piste_ride.piste.id}: {length_meters}m")

            if length_meters > 500 and piste_ride.piste.name:  # Only count named pistes
                # Create unique key for this lap + piste combination
                lap_piste_key = (piste_ride.lap.id, piste_ride.piste.id)

                if lap_piste_key not in seen_lap_piste:
                    seen_lap_piste.add(lap_piste_key)
                    piste_counts[piste_ride.piste.id] += 1
                    logger.debug(f"Added piste to counts: {piste_ride.piste.id} ({piste_ride.piste.name})")
                else:
                    logger.debug(
                        f"Skipping duplicate piste {piste_ride.piste.id} ({piste_ride.piste.name}) in lap {piste_ride.lap.lap_index}"
                    )
        else:
            logger.warning(f"Piste {piste_ride.piste.id} has no geometry")

    logger.info(f"Filtered to {len(piste_counts)} unique named pistes >500m: {dict(piste_counts)}")

    # Only draw if we have either lifts or pistes
    if lift_counts or piste_counts:
        # Prepare data for both columns
        top_lifts = lift_counts.most_common(5) if lift_counts else []
        total_lifts = sum(lift_counts.values()) if lift_counts else 0
        top_lifts_count = sum(count for _, count in top_lifts)
        other_lifts_count = total_lifts - top_lifts_count

        top_pistes = piste_counts.most_common(5) if piste_counts else []
        total_pistes = sum(piste_counts.values()) if piste_counts else 0
        top_pistes_count = sum(count for _, count in top_pistes)
        other_pistes_count = total_pistes - top_pistes_count

        logger.info(f"Top 5 lifts: {top_lifts}")
        logger.info(f"Top 5 pistes: {top_pistes}")

        # Column setup
        column_padding = 60
        column_width = (IMAGE_WIDTH - column_padding * 3) // 2
        left_x = column_padding + column_width // 2
        right_x = column_padding * 2 + column_width + column_width // 2

        # Fonts
        font_item_name = get_font(28)
        line_height = 45

        # Draw column headings
        draw.text((left_x, y_offset), "Top Lifts", fill=hex_to_rgb(COLOR_TEXT_PRIMARY), anchor="mt", font=font_heading)
        draw.text(
            (right_x, y_offset), "Top Pistes", fill=hex_to_rgb(COLOR_TEXT_PRIMARY), anchor="mt", font=font_heading
        )
        y_offset += 60

        # Draw items (up to 5 rows)
        max_items = max(
            len(top_lifts) + (1 if other_lifts_count > 0 else 0), len(top_pistes) + (1 if other_pistes_count > 0 else 0)
        )

        for i in range(max_items):
            # Left column: Lifts
            if i < len(top_lifts):
                lift_name, count = top_lifts[i]
                display_name = lift_name[:18] + "..." if len(lift_name) > 18 else lift_name
                text = f"{count}× {display_name}"
                draw.text(
                    (left_x, y_offset), text, fill=hex_to_rgb(COLOR_TEXT_SECONDARY), anchor="mt", font=font_item_name
                )
            elif i == len(top_lifts) and other_lifts_count > 0:
                text = f"{other_lifts_count}× Other lifts"
                draw.text(
                    (left_x, y_offset), text, fill=hex_to_rgb(COLOR_TEXT_SECONDARY), anchor="mt", font=font_item_name
                )

            # Right column: Pistes
            if i < len(top_pistes):
                piste_id, count = top_pistes[i]
                piste_name = (
                    PisteRide.objects.filter(piste_id=piste_id).first().piste.name
                    or PisteRide.objects.filter(piste_id=piste_id).first().piste.ref
                    or f"unnamed_{piste_id}"
                )
                display_name = piste_name[:18] + "..." if len(piste_name) > 18 else piste_name
                text = f"{count}× {display_name}"
                draw.text(
                    (right_x, y_offset), text, fill=hex_to_rgb(COLOR_TEXT_SECONDARY), anchor="mt", font=font_item_name
                )
            elif i == len(top_pistes) and other_pistes_count > 0:
                text = f"{other_pistes_count}× Other pistes"
                draw.text(
                    (right_x, y_offset), text, fill=hex_to_rgb(COLOR_TEXT_SECONDARY), anchor="mt", font=font_item_name
                )

            y_offset += line_height

        y_offset += 30  # Extra spacing before branding
    else:
        logger.info("No lifts or pistes to display")
        y_offset += 20

    # --- BRANDING SECTION ---
    branding_text = "SlopeLog.com"
    draw.text(
        (IMAGE_WIDTH // 2, IMAGE_HEIGHT - 80),
        branding_text,
        fill=hex_to_rgb(COLOR_TEXT_SECONDARY),
        anchor="mt",
        font=font_branding,
    )

    return img


def _draw_mountain_icon(draw, cx, top_y, size=46):
    """Draw a simple mountain peak icon. cx = horizontal center, top_y = peak y-coordinate."""
    half = size // 2
    draw.polygon(
        [
            (cx, top_y),
            (cx - half, top_y + size),
            (cx + half, top_y + size),
        ],
        fill=hex_to_rgb(COLOR_SEASON_ACCENT),
    )
    # Snow cap (top ~35%)
    cap_h = int(size * 0.35)
    cap_hw = max(4, int(half * 0.42))
    draw.polygon(
        [
            (cx, top_y),
            (cx - cap_hw, top_y + cap_h),
            (cx + cap_hw, top_y + cap_h),
        ],
        fill=(255, 255, 255),
    )


def _draw_horiz_bar(draw, x, y, total_w, h, fill_ratio, fill_color, bg_color="#1e3055"):
    """Draw a rounded horizontal progress bar."""
    r = h // 2
    draw.rounded_rectangle([(x, y), (x + total_w, y + h)], radius=r, fill=hex_to_rgb(bg_color))
    fill_w = max(h, int(total_w * fill_ratio))
    draw.rounded_rectangle([(x, y), (x + fill_w, y + h)], radius=r, fill=hex_to_rgb(fill_color))


def _generate_monthly_pil_bars(draw, x, y, w, h, monthly_stats, accent, gold):
    """
    Draw a minimal bar chart for monthly descent directly with PIL.
    Returns the y offset after drawing.
    """
    if not monthly_stats:
        return y

    max_descent = max((m["descent"] for m in monthly_stats), default=1) or 1
    n = len(monthly_stats)
    gap = max(4, w // (n * 6))
    bar_w = (w - gap * (n + 1)) // n
    label_font = get_font(20)

    for i, month in enumerate(monthly_stats):
        bx = x + gap + i * (bar_w + gap)
        ratio = month["descent"] / max_descent
        bar_h = max(4, int((h - 36) * ratio))
        bar_y = y + (h - 36) - bar_h
        color = gold if month["descent"] == max_descent else accent
        draw.rounded_rectangle(
            [(bx, bar_y), (bx + bar_w, y + h - 36)], radius=max(2, bar_w // 4), fill=hex_to_rgb(color)
        )
        # Month label
        label = month["month"][:3]
        draw.text((bx + bar_w // 2, y + h - 30), label, fill=hex_to_rgb("#64748b"), anchor="mt", font=label_font)

    return y + h


def create_season_share_image(
    season_label,
    season_start,
    season_end,
    stats,
    top_ski_areas,
    best_activity,
    badges_by_rarity,
    total_badge_count,
    monthly_stats,
):
    """
    Create a shareable Instagram story (1080×1920 px) with a full season summary.

    Args:
        season_label:     str like "2025-2026"
        season_start/end: datetime objects for the season boundaries
        stats:            dict – total_activities, total_descent, total_distance_km,
                          total_lift_rides (all numeric, 0 if missing)
        top_ski_areas:    list of dicts {ski_area__name, count}, up to 3
        best_activity:    Activity instance or None (highest single-day descent)
        badges_by_rarity: dict rarity → count
        total_badge_count: int
        monthly_stats:    list of {'month': 'Jan', 'descent': 12000}

    Returns:
        PIL Image (1080×1920 RGB)
    """
    img = Image.new("RGB", (IMAGE_WIDTH, IMAGE_HEIGHT), color=hex_to_rgb(COLOR_SEASON_BG))
    draw = ImageDraw.Draw(img)

    CARD = hex_to_rgb(COLOR_SEASON_CARD)
    ACCENT = hex_to_rgb(COLOR_SEASON_ACCENT)
    GOLD = hex_to_rgb(COLOR_SEASON_GOLD)
    WHITE = hex_to_rgb(COLOR_TEXT_PRIMARY)
    MUTED = hex_to_rgb("#64748b")
    MUTED2 = hex_to_rgb("#94a3b8")
    DIV = hex_to_rgb(COLOR_SEASON_DIVIDER)
    CX = IMAGE_WIDTH // 2

    # Fonts
    f_wordmark = get_font(56, bold=True)
    f_season_yr = get_font(96, bold=True)
    f_hero_num = get_font(86, bold=True)
    f_hero_lbl = get_font(30)
    f_section = get_font(28, bold=True)
    f_stat_val = get_font(58, bold=True)
    f_stat_lbl = get_font(24)
    f_body = get_font(28)
    f_small = get_font(24)
    f_tiny = get_font(20)
    f_branding = get_font(34, bold=True)

    PAD = 72  # side padding

    # ── Sky-blue accent stripe at very top ──────────────────────────────
    draw.rectangle([(0, 0), (IMAGE_WIDTH, 5)], fill=ACCENT)

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 1 — Logo header  (y 5 → ~185)
    # ─────────────────────────────────────────────────────────────────────
    y = 28
    icon_size = 42
    _draw_mountain_icon(draw, CX, y, size=icon_size)
    y += icon_size + 12

    draw.text((CX, y), "SlopeLog", fill=ACCENT, anchor="mt", font=f_wordmark)
    y += 66

    draw.text((CX, y), "S E A S O N   R E C A P", fill=MUTED2, anchor="mt", font=f_tiny)
    y += 34

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 2 — Season year + date range  (~185 → ~370)
    # ─────────────────────────────────────────────────────────────────────
    y += 18
    parts = season_label.split("-")
    year_display = f"{parts[0]} · {parts[1]}" if len(parts) == 2 else season_label
    draw.text((CX, y), year_display, fill=WHITE, anchor="mt", font=f_season_yr)
    y += 108

    try:
        start_str = season_start.strftime("%b %Y")
        end_str = season_end.strftime("%b %Y")
        date_range = f"{start_str}  –  {end_str}"
    except Exception:
        date_range = season_label
    draw.text((CX, y), date_range, fill=MUTED2, anchor="mt", font=f_small)
    y += 44

    # Thin divider
    draw.line([(CX - 80, y), (CX + 80, y)], fill=ACCENT, width=2)
    y += 28

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 3 — Hero descent stat  (~398 → ~618)
    # ─────────────────────────────────────────────────────────────────────
    y += 18
    total_descent = int(stats.get("total_descent") or 0)
    descent_str = f"{total_descent:,} m"

    draw.text((CX, y), "↓", fill=ACCENT, anchor="mt", font=f_hero_num)
    y += 94

    draw.text((CX, y), descent_str, fill=WHITE, anchor="mt", font=f_hero_num)
    y += 98

    draw.text((CX, y), "vertical descent", fill=MUTED2, anchor="mt", font=f_hero_lbl)
    y += 40

    # Everest equivalent
    if total_descent > 0:
        everests = total_descent / 8848
        if everests >= 1.0:
            eq_text = f"≈ {everests:.1f}× the height of Everest"
        else:
            eq_text = f"≈ {total_descent / 1000:.1f} km straight down the mountain"
        draw.text((CX, y), eq_text, fill=GOLD, anchor="mt", font=f_small)
        y += 38
    y += 6

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 4 — Three secondary stats  (~660 → ~800)
    # ─────────────────────────────────────────────────────────────────────
    draw.line([(PAD, y), (IMAGE_WIDTH - PAD, y)], fill=DIV, width=1)
    y += 28

    secondary = [
        (str(int(stats.get("total_activities") or 0)), "Ski Days"),
        (str(int(stats.get("total_lift_rides") or 0)), "Lift Rides"),
        (f"{float(stats.get('total_distance_km') or 0):.0f} km", "Distance"),
    ]
    col_w = IMAGE_WIDTH // 3
    for i, (val, lbl) in enumerate(secondary):
        cx_col = i * col_w + col_w // 2
        if i > 0:
            sep_x = i * col_w
            draw.line([(sep_x, y + 8), (sep_x, y + 104)], fill=DIV, width=1)
        draw.text((cx_col, y + 4), val, fill=WHITE, anchor="mt", font=f_stat_val)
        draw.text((cx_col, y + 74), lbl, fill=MUTED2, anchor="mt", font=f_stat_lbl)

    y += 118
    draw.line([(PAD, y), (IMAGE_WIDTH - PAD, y)], fill=DIV, width=1)
    y += 28

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 5 — Mountains visited  (~846 → ~1080)
    # ─────────────────────────────────────────────────────────────────────
    draw.text((CX, y), "MOUNTAINS VISITED", fill=ACCENT, anchor="mt", font=f_section)
    y += 44

    if top_ski_areas:
        bar_x = PAD
        bar_w = IMAGE_WIDTH - PAD * 2
        bar_h = 16
        max_count = max(a["count"] for a in top_ski_areas)
        area_fills = [COLOR_SEASON_ACCENT, "#60a5fa", "#818cf8"]

        for i, area in enumerate(top_ski_areas[:3]):
            name = (area.get("ski_area__name") or "Unknown Area")[:26]
            count = area["count"]
            ratio = count / max_count if max_count else 0
            fill_col = area_fills[i] if i < len(area_fills) else COLOR_SEASON_ACCENT

            draw.text((bar_x, y), name, fill=WHITE, anchor="lt", font=f_small)
            count_label = f"{count} day{'s' if count != 1 else ''}"
            draw.text((IMAGE_WIDTH - bar_x, y), count_label, fill=MUTED2, anchor="rt", font=f_small)
            y += 30

            _draw_horiz_bar(draw, bar_x, y, bar_w, bar_h, ratio, fill_col)
            y += bar_h + 16

        extra = len(top_ski_areas) - 3
        if extra > 0:
            draw.text(
                (CX, y), f"+ {extra} more mountain{'s' if extra > 1 else ''}", fill=MUTED, anchor="mt", font=f_tiny
            )
            y += 28
    else:
        draw.text((CX, y), "No ski areas recorded", fill=MUTED, anchor="mt", font=f_body)
        y += 38

    draw.line([(PAD, y + 8), (IMAGE_WIDTH - PAD, y + 8)], fill=DIV, width=1)
    y += 36

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 6 — Best day  (~1116 → ~1306)
    # ─────────────────────────────────────────────────────────────────────
    draw.text((CX, y), "BEST DAY", fill=GOLD, anchor="mt", font=f_section)
    y += 44

    card_x = PAD
    card_w = IMAGE_WIDTH - PAD * 2
    card_h = 148
    draw.rounded_rectangle([(card_x, y), (card_x + card_w, y + card_h)], radius=18, fill=CARD)

    if best_activity:
        import pytz

        tz = pytz.timezone(best_activity.timezone) if best_activity.timezone else pytz.UTC
        local_dt = best_activity.start_time.astimezone(tz)
        date_str = local_dt.strftime("%B %d, %Y")
        area_name = (best_activity.ski_area.name if best_activity.ski_area else "Unknown Area")[:24]
        best_desc = int(best_activity.total_descent or 0)
        best_lifts = best_activity.num_lift_rides or 0
        best_dist = round((best_activity.total_distance or 0) / 1000, 1)

        cx_card = card_x + card_w // 2
        draw.text((cx_card, y + 18), f"{date_str}  ·  {area_name}", fill=MUTED2, anchor="mt", font=f_small)
        draw.text((cx_card, y + 54), f"↓ {best_desc:,} m", fill=GOLD, anchor="mt", font=f_stat_val)
        draw.text((cx_card, y + 116), f"{best_lifts} lifts  ·  {best_dist} km", fill=MUTED2, anchor="mt", font=f_small)
    else:
        draw.text(
            (card_x + card_w // 2, y + card_h // 2), "No activities recorded", fill=MUTED, anchor="mm", font=f_body
        )

    y += card_h + 14
    draw.line([(PAD, y + 8), (IMAGE_WIDTH - PAD, y + 8)], fill=DIV, width=1)
    y += 36

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 7 — Month by month  (~1356 → ~1594)
    # ─────────────────────────────────────────────────────────────────────
    draw.text((CX, y), "MONTH BY MONTH", fill=ACCENT, anchor="mt", font=f_section)
    y += 44

    chart_w = IMAGE_WIDTH - PAD * 2
    chart_h = 180
    draw.rounded_rectangle([(PAD, y), (PAD + chart_w, y + chart_h)], radius=16, fill=CARD)

    if monthly_stats:
        _generate_monthly_pil_bars(
            draw, PAD + 16, y + 12, chart_w - 32, chart_h - 12, monthly_stats, COLOR_SEASON_ACCENT, COLOR_SEASON_GOLD
        )
    else:
        draw.text((CX, y + chart_h // 2), "No data", fill=MUTED, anchor="mm", font=f_body)

    y += chart_h + 14
    draw.line([(PAD, y + 8), (IMAGE_WIDTH - PAD, y + 8)], fill=DIV, width=1)
    y += 36

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 8 — Achievements  (~1644 → ~1820)
    # ─────────────────────────────────────────────────────────────────────
    draw.text((CX, y), "ACHIEVEMENTS", fill=ACCENT, anchor="mt", font=f_section)
    y += 44

    rarity_order = ["legendary", "platinum", "gold", "silver", "bronze"]
    earned = [(r, badges_by_rarity[r]) for r in rarity_order if badges_by_rarity.get(r)]

    if earned:
        n_cols = len(earned)
        col_w2 = IMAGE_WIDTH // n_cols
        circle_r = 26

        for i, (rarity, count) in enumerate(earned):
            bx = i * col_w2 + col_w2 // 2
            rc = hex_to_rgb(RARITY_COLORS.get(rarity, "#6c757d"))
            # Filled circle
            draw.ellipse([(bx - circle_r, y), (bx + circle_r, y + circle_r * 2)], fill=rc)
            # Count inside
            draw.text((bx, y + circle_r), str(count), fill=WHITE, anchor="mm", font=f_section)
            # Rarity label below
            draw.text((bx, y + circle_r * 2 + 8), rarity.capitalize(), fill=MUTED2, anchor="mt", font=f_tiny)

        y += circle_r * 2 + 36
        draw.text(
            (CX, y),
            f"{total_badge_count} badge{'s' if total_badge_count != 1 else ''} earned",
            fill=MUTED,
            anchor="mt",
            font=f_small,
        )
        y += 34
    else:
        draw.text((CX, y), "No achievements yet this season", fill=MUTED, anchor="mt", font=f_body)
        y += 38

    # ─────────────────────────────────────────────────────────────────────
    # FOOTER — always pinned to bottom of canvas
    # ─────────────────────────────────────────────────────────────────────
    footer_y = IMAGE_HEIGHT - 82
    draw.rectangle([(0, footer_y - 1), (IMAGE_WIDTH, IMAGE_HEIGHT)], fill=hex_to_rgb("#070c17"))
    draw.line([(0, footer_y - 1), (IMAGE_WIDTH, footer_y - 1)], fill=ACCENT, width=2)
    draw.text((CX, footer_y + 12), "slopelog.com", fill=ACCENT, anchor="mt", font=f_branding)
    draw.text((CX, footer_y + 54), "✦  Premium Season Summary  ✦", fill=MUTED, anchor="mt", font=f_tiny)

    return img


def generate_season_share_image_bytes(
    season_label,
    season_start,
    season_end,
    stats,
    top_ski_areas,
    best_activity,
    badges_by_rarity,
    total_badge_count,
    monthly_stats,
):
    """
    Generate season summary image and return as a BytesIO PNG.
    Raises on failure.
    """
    img = create_season_share_image(
        season_label=season_label,
        season_start=season_start,
        season_end=season_end,
        stats=stats,
        top_ski_areas=top_ski_areas,
        best_activity=best_activity,
        badges_by_rarity=badges_by_rarity,
        total_badge_count=total_badge_count,
        monthly_stats=monthly_stats,
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


def generate_activity_share_image_bytes(activity):
    """
    Generate shareable activity image and return as bytes.

    Args:
        activity: Activity model instance

    Returns:
        BytesIO object containing PNG image data
    """
    try:
        img = create_shareable_image(activity)

        # Convert to bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG", optimize=True)
        img_bytes.seek(0)

        return img_bytes

    except Exception as e:
        logger.error(f"Error generating shareable image for activity {activity.id}: {e}")
        raise
