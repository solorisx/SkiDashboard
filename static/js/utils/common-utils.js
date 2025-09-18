/**
 * Common Utilities
 * Reusable JavaScript utilities and helpers
 */

const CommonUtils = {
  /**
   * Initialize common components across all pages
   */
  init() {
    this.initTooltips();
    this.initPopovers();
    this.initScrollToTop();
    this.initLazyLoading();
    this.initKeyboardNavigation();
  },

  /**
   * Initialize Bootstrap tooltips globally
   */
  initTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    const tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
      return new bootstrap.Tooltip(tooltipTriggerEl, {
        boundary: 'viewport',
        customClass: 'custom-tooltip'
      });
    });

    // Store references for cleanup
    window.activeTooltips = tooltipList;
  },

  /**
   * Initialize Bootstrap popovers
   */
  initPopovers() {
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    const popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
      return new bootstrap.Popover(popoverTriggerEl, {
        boundary: 'viewport',
        customClass: 'custom-popover'
      });
    });

    // Store references for cleanup
    window.activePopovers = popoverList;
  },

  /**
   * Initialize scroll to top functionality
   */
  initScrollToTop() {
    // Create scroll to top button if it doesn't exist
    if (!document.getElementById('scrollToTop')) {
      const scrollBtn = document.createElement('button');
      scrollBtn.id = 'scrollToTop';
      scrollBtn.className = 'btn btn-primary position-fixed';
      scrollBtn.style.cssText = `
        bottom: 2rem;
        right: 2rem;
        z-index: 1050;
        border-radius: 50%;
        width: 50px;
        height: 50px;
        opacity: 0;
        visibility: hidden;
        transition: all 0.3s ease;
        box-shadow: 0 4px 12px rgba(0,123,255,0.3);
      `;
      scrollBtn.innerHTML = '<i class="bi bi-arrow-up"></i>';
      scrollBtn.setAttribute('aria-label', 'Scroll to top');
      document.body.appendChild(scrollBtn);

      // Show/hide on scroll
      window.addEventListener('scroll', this.debounce(() => {
        const isVisible = window.pageYOffset > 300;
        scrollBtn.style.opacity = isVisible ? '1' : '0';
        scrollBtn.style.visibility = isVisible ? 'visible' : 'hidden';
      }, 100));

      // Smooth scroll to top
      scrollBtn.addEventListener('click', () => {
        window.scrollTo({
          top: 0,
          behavior: 'smooth'
        });
      });
    }
  },

  /**
   * Initialize lazy loading for images
   */
  initLazyLoading() {
    if ('IntersectionObserver' in window) {
      const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            const img = entry.target;
            img.src = img.dataset.src;
            img.classList.remove('lazy');
            imageObserver.unobserve(img);
          }
        });
      });

      document.querySelectorAll('img[data-src]').forEach(img => {
        imageObserver.observe(img);
      });
    }
  },

  /**
   * Enhanced keyboard navigation
   */
  initKeyboardNavigation() {
    // Handle Escape key globally
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        // Close any open modals
        const openModal = document.querySelector('.modal.show');
        if (openModal) {
          bootstrap.Modal.getInstance(openModal)?.hide();
          return;
        }

        // Close any open dropdowns
        const openDropdown = document.querySelector('.dropdown-menu.show');
        if (openDropdown) {
          bootstrap.Dropdown.getInstance(openDropdown.previousElementSibling)?.hide();
          return;
        }

        // Clear focus from search inputs
        const activeElement = document.activeElement;
        if (activeElement && activeElement.type === 'search') {
          activeElement.blur();
        }
      }
    });

    // Add keyboard navigation to cards
    document.querySelectorAll('.card[tabindex]').forEach(card => {
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          const link = card.querySelector('a');
          if (link) {
            link.click();
          }
        }
      });
    });
  },

  /**
   * Debounce function for performance
   */
  debounce(func, wait, immediate) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        timeout = null;
        if (!immediate) func(...args);
      };
      const callNow = immediate && !timeout;
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
      if (callNow) func(...args);
    };
  },

  /**
   * Throttle function for performance
   */
  throttle(func, limit) {
    let inThrottle;
    return function(...args) {
      if (!inThrottle) {
        func.apply(this, args);
        inThrottle = true;
        setTimeout(() => inThrottle = false, limit);
      }
    };
  },

  /**
   * Format numbers with locale-specific formatting
   */
  formatNumber(num, options = {}) {
    const defaults = {
      minimumFractionDigits: 0,
      maximumFractionDigits: 1
    };

    return new Intl.NumberFormat('en-US', { ...defaults, ...options }).format(num);
  },

  /**
   * Format bytes to human readable format
   */
  formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 Bytes';

    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];

    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  },

  /**
   * Copy text to clipboard
   */
  async copyToClipboard(text) {
    try {
      await navigator.clipboard.writeText(text);
      this.showToast('Copied to clipboard!', 'success');
      return true;
    } catch (err) {
      console.error('Failed to copy: ', err);
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      try {
        document.execCommand('copy');
        this.showToast('Copied to clipboard!', 'success');
        return true;
      } catch (fallbackErr) {
        console.error('Fallback copy failed: ', fallbackErr);
        this.showToast('Failed to copy to clipboard', 'error');
        return false;
      } finally {
        document.body.removeChild(textArea);
      }
    }
  },

  /**
   * Show toast notification
   */
  showToast(message, type = 'info', duration = 3000) {
    // Create toast container if it doesn't exist
    let toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
      toastContainer = document.createElement('div');
      toastContainer.id = 'toast-container';
      toastContainer.className = 'position-fixed top-0 end-0 p-3';
      toastContainer.style.zIndex = '1060';
      document.body.appendChild(toastContainer);
    }

    // Create toast element
    const toastEl = document.createElement('div');
    toastEl.className = `toast align-items-center text-white bg-${type === 'success' ? 'success' : type === 'error' ? 'danger' : 'primary'} border-0`;
    toastEl.setAttribute('role', 'alert');
    toastEl.innerHTML = `
      <div class="d-flex">
        <div class="toast-body">${message}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
      </div>
    `;

    toastContainer.appendChild(toastEl);

    // Initialize and show toast
    const toast = new bootstrap.Toast(toastEl, { delay: duration });
    toast.show();

    // Remove from DOM after hiding
    toastEl.addEventListener('hidden.bs.toast', () => {
      toastEl.remove();
    });
  },

  /**
   * Generate unique ID
   */
  generateId(prefix = 'id') {
    return `${prefix}_${Math.random().toString(36).substr(2, 9)}`;
  },

  /**
   * Check if element is in viewport
   */
  isInViewport(element) {
    const rect = element.getBoundingClientRect();
    return (
      rect.top >= 0 &&
      rect.left >= 0 &&
      rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
      rect.right <= (window.innerWidth || document.documentElement.clientWidth)
    );
  },

  /**
   * Smooth scroll to element
   */
  scrollToElement(element, offset = 0) {
    const elementPosition = element.offsetTop;
    const offsetPosition = elementPosition - offset;

    window.scrollTo({
      top: offsetPosition,
      behavior: 'smooth'
    });
  },

  /**
   * Get URL parameters
   */
  getUrlParams() {
    return new URLSearchParams(window.location.search);
  },

  /**
   * Update URL without page reload
   */
  updateUrl(params, title = null) {
    const url = new URL(window.location);

    Object.entries(params).forEach(([key, value]) => {
      if (value === null || value === undefined || value === '') {
        url.searchParams.delete(key);
      } else {
        url.searchParams.set(key, value);
      }
    });

    window.history.replaceState({}, title || document.title, url);
  },

  /**
   * Cleanup function for page unload
   */
  cleanup() {
    // Dispose tooltips
    if (window.activeTooltips) {
      window.activeTooltips.forEach(tooltip => tooltip.dispose());
      window.activeTooltips = [];
    }

    // Dispose popovers
    if (window.activePopovers) {
      window.activePopovers.forEach(popover => popover.dispose());
      window.activePopovers = [];
    }
  }
};

// Auto-initialize common utilities
document.addEventListener('DOMContentLoaded', () => {
  CommonUtils.init();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
  CommonUtils.cleanup();
});

// Export for global use
window.CommonUtils = CommonUtils;

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = CommonUtils;
}