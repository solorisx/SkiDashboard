/**
 * Activity Card Components JavaScript
 * Reusable functionality extracted from activity_list.html
 */

class ActivityCardManager {
  constructor() {
    this.tooltips = [];
    this.completenessCards = new Map();
  }

  /**
   * Initialize all activity card components
   */
  init() {
    this.initTooltips();
    this.initCompletenessCards();
    this.initMaps();
    this.initHoverEffects();
  }

  /**
   * Initialize Bootstrap tooltips
   */
  initTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    this.tooltips = tooltipTriggerList.map(function (tooltipTriggerEl) {
      return new bootstrap.Tooltip(tooltipTriggerEl);
    });
  }

  /**
   * Initialize completeness cards with AJAX loading
   */
  initCompletenessCards() {
    const completenessCards = document.querySelectorAll('[id^="completeness-"]');

    completenessCards.forEach(card => {
      const activityId = card.dataset.activityId;
      const skiAreaId = card.dataset.skiAreaId;

      if (!activityId || !skiAreaId) return;

      this.loadActivityCompleteness(card, activityId, skiAreaId);
    });
  }

  /**
   * Load activity completeness data via AJAX
   */
  async loadActivityCompleteness(card, activityId, skiAreaId) {
    try {
      const response = await fetch(`/activities/api/activity-completeness/${activityId}/`, {
        method: 'GET',
        headers: {
          'X-Requested-With': 'XMLHttpRequest'
        }
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const data = await response.json();
      this.renderCompletenessCard(card, data, skiAreaId);
    } catch (error) {
      console.error('Error loading completeness:', error);
      this.renderCompletenessError(card);
    }
  }

  /**
   * Render completeness card with data
   */
  renderCompletenessCard(card, data, skiAreaId) {
    const percentage = Math.round(data.daily_completion_percentage || 0);
    const liftsUsed = data.lifts_used_today || 0;
    const totalLifts = data.total_lifts_available || 0;
    const newLifts = data.new_lifts_discovered || 0;

    const { badgeClass, badgeIcon } = this.getCompletenessStyle(percentage);

    card.innerHTML = `
      <a href="/activities/ski-area-completeness/${skiAreaId}/" class="text-decoration-none">
        <div class="d-flex align-items-center justify-content-between">
          <div class="text-start">
            <div class="fs-5 fw-bold text-${badgeClass} mb-0">${percentage}%</div>
            <small class="text-muted fw-medium">Area completeness</small>
          </div>
          <div class="text-end">
            <div class="d-flex align-items-center gap-1 mb-1">
              <i class="bi bi-${badgeIcon} text-${badgeClass}"></i>
              <small class="text-muted">${liftsUsed}/${totalLifts} lifts</small>
            </div>
            <div class="mb-1" style="min-height: 20px;">
              ${newLifts > 0 ? `<div class="badge bg-success text-white small">+${newLifts} new!</div>` : ''}
            </div>
            <div class="text-center">
              <small class="text-primary fw-medium">
                <i class="bi bi-arrow-right me-1"></i>View Details
              </small>
            </div>
          </div>
        </div>
      </a>
    `;

    // Add hover effect
    card.classList.add('hover-lift-completeness');
  }

  /**
   * Render error state for completeness card
   */
  renderCompletenessError(card) {
    card.innerHTML = `
      <div class="text-center">
        <small class="text-muted">Completeness unavailable</small>
      </div>
    `;
  }

  /**
   * Get styling classes based on completion percentage
   */
  getCompletenessStyle(percentage) {
    let badgeClass = 'secondary';
    if (percentage >= 75) badgeClass = 'success';
    else if (percentage >= 50) badgeClass = 'warning';
    else if (percentage >= 25) badgeClass = 'info';

    let badgeIcon = 'pie-chart';
    if (percentage >= 75) badgeIcon = 'trophy';
    else if (percentage >= 50) badgeIcon = 'award';

    return { badgeClass, badgeIcon };
  }

  /**
   * Initialize Leaflet maps for activities
   */
  initMaps() {
    // Check if Leaflet is available
    if (typeof L === 'undefined') {
      console.warn('Leaflet not loaded, skipping map initialization');
      return;
    }

    const maps = document.querySelectorAll('[id^="map"]');
    maps.forEach((mapElement, index) => {
      this.initSingleMap(mapElement, index);
    });
  }

  /**
   * Initialize a single Leaflet map
   */
  initSingleMap(mapElement, index) {
    const activityData = this.getActivityDataForMap(mapElement);

    if (!activityData) {
      this.renderMapPlaceholder(mapElement);
      return;
    }

    try {
      const map = L.map(mapElement.id, {
        zoomControl: false,
        attributionControl: false,
        scrollWheelZoom: false,
        doubleClickZoom: false,
        touchZoom: false,
        dragging: false,
        boxZoom: false,
        keyboard: false
      }).setView([activityData.lat, activityData.lng], 13);

      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: false
      }).addTo(map);

      if (activityData.track) {
        const trackLayer = L.geoJSON(activityData.track, {
          style: {
            color: '#0d6efd',
            weight: 4,
            opacity: 0.8,
            lineCap: 'round',
            lineJoin: 'round'
          }
        }).addTo(map);

        map.fitBounds(trackLayer.getBounds(), { padding: [10, 10] });
      }
    } catch (error) {
      console.error('Error initializing map:', error);
      this.renderMapPlaceholder(mapElement);
    }
  }

  /**
   * Get activity data for map from data attributes or global variables
   */
  getActivityDataForMap(mapElement) {
    // This would be implemented based on how activity data is passed to the template
    // For now, return null to trigger placeholder
    return null;
  }

  /**
   * Render map placeholder when no data available
   */
  renderMapPlaceholder(mapElement) {
    mapElement.innerHTML = `
      <div class="mini-map-placeholder">
        <div class="text-center">
          <i class="bi bi-geo-alt display-4 mb-2"></i><br>
          <small>No map data available</small>
        </div>
      </div>
    `;
  }

  /**
   * Initialize enhanced hover effects
   */
  initHoverEffects() {
    // Add smooth transitions to cards that don't have them
    const cards = document.querySelectorAll('.card:not(.activity-card)');
    cards.forEach(card => {
      if (!card.style.transition) {
        card.style.transition = 'all 0.3s ease';
      }
    });

    // Add hover effects to stat cards
    const statCards = document.querySelectorAll('.stats-card');
    statCards.forEach(card => {
      card.addEventListener('mouseenter', () => {
        card.style.transform = 'scale(1.02)';
      });

      card.addEventListener('mouseleave', () => {
        card.style.transform = 'scale(1)';
      });
    });
  }

  /**
   * Cleanup method to remove event listeners and tooltips
   */
  destroy() {
    this.tooltips.forEach(tooltip => {
      tooltip.dispose();
    });
    this.tooltips = [];
    this.completenessCards.clear();
  }
}

/**
 * Utility functions for activity cards
 */
const ActivityCardUtils = {
  /**
   * Format numbers with appropriate suffixes (K, M, etc.)
   */
  formatNumber(num) {
    if (num >= 1000000) {
      return (num / 1000000).toFixed(1) + 'M';
    }
    if (num >= 1000) {
      return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
  },

  /**
   * Get color class based on value and thresholds
   */
  getValueColorClass(value, thresholds = { high: 75, medium: 50, low: 25 }) {
    if (value >= thresholds.high) return 'success';
    if (value >= thresholds.medium) return 'warning';
    if (value >= thresholds.low) return 'info';
    return 'secondary';
  },

  /**
   * Create loading spinner HTML
   */
  createLoadingSpinner(text = 'Loading...') {
    return `
      <div class="completeness-loading">
        <div class="spinner-border spinner-border-sm text-secondary" role="status">
          <span class="visually-hidden">Loading...</span>
        </div>
        <small class="text-muted fw-medium">${text}</small>
      </div>
    `;
  },

  /**
   * Debounce function for performance
   */
  debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }
};

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
  window.activityCardManager = new ActivityCardManager();
  window.activityCardManager.init();
});

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { ActivityCardManager, ActivityCardUtils };
}