"""
Utility for generating shareable activity images with stats and mini map.
"""

import io
import logging
from datetime import timedelta
from PIL import Image, ImageDraw, ImageFont
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from django.contrib.gis.geos import LineString

logger = logging.getLogger(__name__)

# Image dimensions for Instagram story format
IMAGE_WIDTH = 1080
IMAGE_HEIGHT = 1920

# Color scheme
COLOR_BG = '#1a1a2e'  # Dark blue background
COLOR_TEXT_PRIMARY = '#ffffff'
COLOR_TEXT_SECONDARY = '#a0a0b0'
COLOR_ACCENT = '#0d6efd'  # Bootstrap primary blue
COLOR_SUCCESS = '#198754'
COLOR_WARNING = '#ffc107'
COLOR_CARD_BG = '#2a2a3e'


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
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


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
        fig, ax = plt.subplots(figsize=(size[0]/100, size[1]/100), dpi=100)
        fig.patch.set_facecolor(COLOR_CARD_BG)
        ax.set_facecolor(COLOR_BG)

        # Remove all margins and padding
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

        # Plot the track
        ax.plot(lons, lats, color=COLOR_ACCENT, linewidth=3, alpha=0.9,
                solid_capstyle='round', solid_joinstyle='round')

        # Add start point marker (green)
        ax.plot(lons[0], lats[0], 'o', color=COLOR_SUCCESS, markersize=12,
                markeredgewidth=2, markeredgecolor='white', zorder=5)

        # Add end point marker (red)
        ax.plot(lons[-1], lats[-1], 's', color='#dc3545', markersize=12,
                markeredgewidth=2, markeredgecolor='white', zorder=5)

        # Remove axes
        ax.set_xticks([])
        ax.set_yticks([])
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        ax.spines['left'].set_visible(False)

        # Add some padding
        x_range = max(lons) - min(lons)
        y_range = max(lats) - min(lats)
        padding = 0.1  # 10% padding
        ax.set_xlim(min(lons) - x_range * padding, max(lons) + x_range * padding)
        ax.set_ylim(min(lats) - y_range * padding, max(lats) + y_range * padding)

        # Set aspect ratio to 'auto' to fill the entire rectangle
        ax.set_aspect('auto')

        # Convert matplotlib figure to PIL Image
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches=None, pad_inches=0,
                   facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)
        buf.seek(0)

        return Image.open(buf)

    except Exception as e:
        logger.error(f"Error generating map for activity {activity.id}: {e}")
        return _create_placeholder_map(size)


def _create_placeholder_map(size):
    """Create a placeholder map image when actual map cannot be generated."""
    img = Image.new('RGB', size, color=hex_to_rgb(COLOR_CARD_BG))
    draw = ImageDraw.Draw(img)

    # Draw a simple placeholder
    center_x, center_y = size[0] // 2, size[1] // 2
    draw.text((center_x, center_y), "Map Unavailable",
             fill=hex_to_rgb(COLOR_TEXT_SECONDARY), anchor="mm",
             font=get_font(24))

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
    img = Image.new('RGB', (IMAGE_WIDTH, IMAGE_HEIGHT), color=hex_to_rgb(COLOR_BG))
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

    draw.text((IMAGE_WIDTH // 2, y_offset), activity_name,
             fill=hex_to_rgb(COLOR_TEXT_PRIMARY), anchor="mt", font=font_title)
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
        [(badge_x, badge_y), (badge_x + badge_width, badge_y + badge_height)],
        radius=25, fill=hex_to_rgb(COLOR_ACCENT)
    )
    draw.text((IMAGE_WIDTH // 2, badge_y + badge_height // 2),
             ski_area_name, fill=hex_to_rgb(COLOR_TEXT_PRIMARY),
             anchor="mm", font=font_small)
    y_offset += badge_height + 40

    # Date
    from django.utils import timezone
    import pytz

    # Convert to activity timezone for display
    activity_tz = pytz.timezone(activity.timezone) if activity.timezone else timezone.get_current_timezone()
    local_time = activity.start_time.astimezone(activity_tz)
    date_str = local_time.strftime("%B %d, %Y")

    draw.text((IMAGE_WIDTH // 2, y_offset), date_str,
             fill=hex_to_rgb(COLOR_TEXT_SECONDARY), anchor="mt", font=font_small)
    y_offset += 80

    # --- MINI MAP SECTION ---
    map_size = 500  # Reduced from 600 to 500
    map_img = generate_activity_map(activity, size=(map_size, map_size))
    map_x = (IMAGE_WIDTH - map_size) // 2
    map_y = y_offset

    # Add border around map
    border_width = 4
    draw.rounded_rectangle(
        [(map_x - border_width, map_y - border_width),
         (map_x + map_size + border_width, map_y + map_size + border_width)],
        radius=20, fill=hex_to_rgb(COLOR_CARD_BG)
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

    lifts_used = lift_completeness.get('lifts_used_today', 0)
    total_lifts = lift_completeness.get('total_lifts_available', 0)

    distance_skied_km = int(round(piste_completeness.get('distance_skied_today', 0) / 1000))
    total_distance_km = int(round(piste_completeness.get('total_distance_available', 0) / 1000))
    
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
            [(card_x, card_y), (card_x + card_width, card_y + card_height)],
            radius=15, fill=hex_to_rgb(COLOR_CARD_BG)
        )

        # Use smaller font for completeness stats (last 2 rows) which have more text
        # value_font = font_heading if idx >= 4 else font_stat_value
        value_font = font_stat_value

        # Draw value
        draw.text((card_x + card_width // 2, card_y + 60),
                 value, fill=hex_to_rgb(color), anchor="mt", font=value_font)

        # Draw label
        draw.text((card_x + card_width // 2, card_y + 140),
                 label, fill=hex_to_rgb(COLOR_TEXT_SECONDARY),
                 anchor="mt", font=font_stat_label)

    y_offset += 3 * (card_height + 20) + 40  # Reduced from 60 to 40

    # --- TOP LIFTS & PISTES SECTION (TWO COLUMNS) ---
    from collections import Counter
    from activities.models import PisteRide

    # Get lift rides for this activity
    lift_counts = Counter()
    for lap in activity.laps.all():
        for lift_ride in lap.liftride_set.select_related('aerialway').all():
            if lift_ride.aerialway:
                lift_name = lift_ride.aerialway.name or f"Lift {lift_ride.aerialway.id}"
                lift_counts[lift_name] += 1

    # Get piste rides for this activity (>500m only)
    piste_rides = PisteRide.objects.filter(
        lap__activity=activity
    ).select_related('piste', 'piste__way', 'lap').order_by('lap__lap_index', 'timestamp')

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
                    logger.debug(f"Skipping duplicate piste {piste_ride.piste.id} ({piste_ride.piste.name}) in lap {piste_ride.lap.lap_index}")
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
        draw.text((left_x, y_offset), "Top Lifts",
                 fill=hex_to_rgb(COLOR_TEXT_PRIMARY), anchor="mt", font=font_heading)
        draw.text((right_x, y_offset), "Top Pistes",
                 fill=hex_to_rgb(COLOR_TEXT_PRIMARY), anchor="mt", font=font_heading)
        y_offset += 60

        # Draw items (up to 5 rows)
        max_items = max(len(top_lifts) + (1 if other_lifts_count > 0 else 0),
                       len(top_pistes) + (1 if other_pistes_count > 0 else 0))

        for i in range(max_items):
            # Left column: Lifts
            if i < len(top_lifts):
                lift_name, count = top_lifts[i]
                display_name = lift_name[:18] + "..." if len(lift_name) > 18 else lift_name
                text = f"{count}× {display_name}"
                draw.text((left_x, y_offset), text,
                         fill=hex_to_rgb(COLOR_TEXT_SECONDARY), anchor="mt", font=font_item_name)
            elif i == len(top_lifts) and other_lifts_count > 0:
                text = f"{other_lifts_count}× Other lifts"
                draw.text((left_x, y_offset), text,
                         fill=hex_to_rgb(COLOR_TEXT_SECONDARY), anchor="mt", font=font_item_name)

            # Right column: Pistes
            if i < len(top_pistes):
                piste_id, count = top_pistes[i]
                piste_name = PisteRide.objects.filter(piste_id=piste_id).first().piste.name or PisteRide.objects.filter(piste_id=piste_id).first().piste.ref or f"unnamed_{piste_id}"
                display_name = piste_name[:18] + "..." if len(piste_name) > 18 else piste_name
                text = f"{count}× {display_name}"
                draw.text((right_x, y_offset), text,
                         fill=hex_to_rgb(COLOR_TEXT_SECONDARY), anchor="mt", font=font_item_name)
            elif i == len(top_pistes) and other_pistes_count > 0:
                text = f"{other_pistes_count}× Other pistes"
                draw.text((right_x, y_offset), text,
                         fill=hex_to_rgb(COLOR_TEXT_SECONDARY), anchor="mt", font=font_item_name)

            y_offset += line_height

        y_offset += 30  # Extra spacing before branding
    else:
        logger.info("No lifts or pistes to display")
        y_offset += 20

    # --- BRANDING SECTION ---
    branding_text = "SlopeLog.com"
    draw.text((IMAGE_WIDTH // 2, IMAGE_HEIGHT - 80), branding_text,
             fill=hex_to_rgb(COLOR_TEXT_SECONDARY), anchor="mt", font=font_branding)

    return img


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
        img.save(img_bytes, format='PNG', optimize=True)
        img_bytes.seek(0)

        return img_bytes

    except Exception as e:
        logger.error(f"Error generating shareable image for activity {activity.id}: {e}")
        raise
