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

        # Create figure
        fig, ax = plt.subplots(figsize=(size[0]/100, size[1]/100), dpi=100)
        fig.patch.set_facecolor(COLOR_CARD_BG)
        ax.set_facecolor(COLOR_BG)

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

        # Ensure equal aspect ratio
        ax.set_aspect('equal')

        # Convert matplotlib figure to PIL Image
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight',
                   facecolor=fig.get_facecolor(), edgecolor='none', pad_inches=0.1)
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
    map_size = 600
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
    y_offset += map_size + 60

    # --- STATISTICS SECTION ---
    # Calculate stats
    distance_km = round(activity.total_distance / 1000, 1) if activity.total_distance else 0
    descent_m = round(activity.total_descent) if activity.total_descent else 0
    num_lifts = activity.num_lift_rides if activity.num_lift_rides else 0
    duration = format_duration(activity.total_elapsed_time)

    # Create stats grid (2x2)
    stats = [
        ("Distance", f"{distance_km} km", COLOR_ACCENT),
        ("Descent", f"{descent_m} m", COLOR_SUCCESS),
        ("Lifts", f"{num_lifts}", COLOR_WARNING),
        ("Duration", duration, "#17a2b8"),  # Info color
    ]

    # Grid layout
    grid_padding = 40
    card_width = (IMAGE_WIDTH - grid_padding * 3) // 2
    card_height = 180

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

        # Draw value
        draw.text((card_x + card_width // 2, card_y + 60),
                 value, fill=hex_to_rgb(color), anchor="mt", font=font_stat_value)

        # Draw label
        draw.text((card_x + card_width // 2, card_y + 140),
                 label, fill=hex_to_rgb(COLOR_TEXT_SECONDARY),
                 anchor="mt", font=font_stat_label)

    y_offset += 2 * (card_height + 20) + 60

    # --- TOP LIFTS SECTION ---
    from collections import Counter

    # Get lift rides for this activity
    lift_counts = Counter()

    # Query lift rides through laps (use liftride_set to access the through model)
    for lap in activity.laps.all():
        for lift_ride in lap.liftride_set.select_related('aerialway').all():
            if lift_ride.aerialway:
                lift_name = lift_ride.aerialway.name or f"Lift {lift_ride.aerialway.id}"
                lift_counts[lift_name] += 1

    if lift_counts:
        # Get top 5 lifts
        top_lifts = lift_counts.most_common(5)
        total_lifts = sum(lift_counts.values())
        top_lifts_count = sum(count for _, count in top_lifts)
        other_lifts_count = total_lifts - top_lifts_count

        # Draw top lifts section heading
        draw.text((IMAGE_WIDTH // 2, y_offset), "Top Lifts",
                 fill=hex_to_rgb(COLOR_TEXT_PRIMARY), anchor="mt", font=font_heading)
        y_offset += 60

        # Draw lift list with counts
        font_lift_count = get_font(36, bold=True)
        font_lift_name = get_font(32)
        line_height = 50

        for lift_name, count in top_lifts:
            # Truncate long lift names
            display_name = lift_name[:35] + "..." if len(lift_name) > 35 else lift_name

            # Draw count and lift name
            text = f"{count}× {display_name}"
            draw.text((IMAGE_WIDTH // 2, y_offset), text,
                     fill=hex_to_rgb(COLOR_TEXT_SECONDARY), anchor="mt", font=font_lift_name)
            y_offset += line_height

        # Add "other lifts" if there are more than 5 unique lifts
        if other_lifts_count > 0:
            text = f"{other_lifts_count}× Other lifts"
            draw.text((IMAGE_WIDTH // 2, y_offset), text,
                     fill=hex_to_rgb(COLOR_TEXT_SECONDARY), anchor="mt", font=font_lift_name)
            y_offset += line_height

        y_offset += 40  # Extra spacing before branding

    # --- BRANDING SECTION ---
    branding_text = "SkiDashboard.com"
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
