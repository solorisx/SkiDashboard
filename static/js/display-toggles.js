/**
 * Reusable Display Toggle Functionality
 * Handles view mode switching and collapsible sections
 */

class DisplayToggle {
  constructor(options = {}) {
    this.storageKey = options.storageKey || 'display-mode';
    this.collapsedStorageKey = options.collapsedStorageKey || 'collapsed-sections';
    this.fadeTransitionTime = options.fadeTransitionTime || 200;
    
    this.init();
  }
  
  init() {
    this.restoreDisplayMode();
    this.restoreCollapsedSections();
  }
  
  /**
   * Toggle between different display modes (list, grouped, etc.)
   */
  toggleDisplayMode(mode) {
    const container = document.getElementById('display-container');
    if (!container) return;
    
    // Find all view containers
    const views = container.querySelectorAll('[id$="-view"]');
    if (views.length === 0) return;
    
    // Add fade transition
    container.classList.add('display-mode-container', 'fade-out');
    
    setTimeout(() => {
      // Hide all views
      views.forEach(view => view.classList.add('d-none'));
      
      // Show selected view
      const targetView = document.getElementById(mode + '-view');
      if (targetView) {
        targetView.classList.remove('d-none');
      }
      
      // Fade back in
      container.classList.remove('fade-out');
    }, this.fadeTransitionTime);
    
    // Store preference
    localStorage.setItem(this.storageKey, mode);
    
    // Update radio buttons
    this.updateRadioButtons(mode);
  }
  
  /**
   * Update radio button states for display mode
   */
  updateRadioButtons(mode) {
    const radios = document.querySelectorAll('input[name="display-mode"]');
    radios.forEach(radio => {
      radio.checked = radio.id === 'display-' + mode;
    });
  }
  
  /**
   * Toggle collapsible section
   */
  toggleSection(sectionId) {
    const section = document.getElementById('section-' + sectionId);
    const toggleButton = document.querySelector(`[onclick*="${sectionId}"]`);
    
    if (!section || !toggleButton) return;
    
    const isCollapsed = section.classList.contains('collapsed');
    
    if (isCollapsed) {
      // Expand
      section.classList.remove('collapsed');
      toggleButton.classList.remove('collapsed');
    } else {
      // Collapse
      section.classList.add('collapsed');
      toggleButton.classList.add('collapsed');
    }
    
    // Update storage
    this.updateCollapsedSections(sectionId, !isCollapsed);
  }
  
  /**
   * Update collapsed sections in localStorage
   */
  updateCollapsedSections(sectionId, isCollapsed) {
    const collapsedSections = JSON.parse(localStorage.getItem(this.collapsedStorageKey) || '[]');
    const index = collapsedSections.indexOf(sectionId);
    
    if (isCollapsed && index === -1) {
      collapsedSections.push(sectionId);
    } else if (!isCollapsed && index > -1) {
      collapsedSections.splice(index, 1);
    }
    
    localStorage.setItem(this.collapsedStorageKey, JSON.stringify(collapsedSections));
  }
  
  /**
   * Restore display mode from localStorage
   */
  restoreDisplayMode() {
    const savedMode = localStorage.getItem(this.storageKey);
    if (!savedMode) return;
    
    const radio = document.getElementById('display-' + savedMode);
    if (radio && !radio.checked) {
      radio.checked = true;
      this.toggleDisplayMode(savedMode);
    }
  }
  
  /**
   * Restore collapsed sections from localStorage
   */
  restoreCollapsedSections() {
    const collapsedSections = JSON.parse(localStorage.getItem(this.collapsedStorageKey) || '[]');
    
    collapsedSections.forEach(sectionId => {
      const section = document.getElementById('section-' + sectionId);
      const toggleButton = document.querySelector(`[onclick*="${sectionId}"]`);
      
      if (section && toggleButton) {
        section.classList.add('collapsed');
        toggleButton.classList.add('collapsed');
      }
    });
  }
}

// Global functions for backward compatibility and ease of use
let displayToggle;

function toggleDisplayMode(mode) {
  if (!displayToggle) {
    displayToggle = new DisplayToggle();
  }
  displayToggle.toggleDisplayMode(mode);
}

function toggleSection(sectionId) {
  if (!displayToggle) {
    displayToggle = new DisplayToggle();
  }
  displayToggle.toggleSection(sectionId);
}

// Legacy function name for lift rides
function toggleSkiAreaSection(sectionId) {
  toggleSection(sectionId);
}

// Auto-initialize on page load
document.addEventListener('DOMContentLoaded', function() {
  displayToggle = new DisplayToggle({
    storageKey: 'lift-display-mode',
    collapsedStorageKey: 'collapsed-ski-areas'
  });
});