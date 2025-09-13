/**
 * Cost Home Page JavaScript
 * Handles season pass management (create, edit, delete) with modal interactions
 */

// Toggle SkiArea vs Network controls in Add/Edit modals
function toggleType(sectionPrefix, type) {
  const skiareaWrap = document.getElementById(sectionPrefix + 'SkiareaWrap');
  const networkWrap = document.getElementById(sectionPrefix + 'NetworkWrap');
  if (type === 'skiarea') {
    skiareaWrap.classList.remove('d-none');
    networkWrap.classList.add('d-none');
  } else {
    networkWrap.classList.remove('d-none');
    skiareaWrap.classList.add('d-none');
  }
}

// Helper: Get CSRF token (needed if using Django templates & CSRF middleware)
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";");
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + "=")) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

// Helper: Set value of select2 or DAL select, creating option if needed
function setSelect2Value(selectEl, id, text) {
  const $sel = window.jQuery ? jQuery(selectEl) : null;
  if (!id) {
    if ($sel) $sel.val(null).trigger('change');
    else selectEl.value = '';
    return;
  }
  // If option doesn't exist, create it
  if (!Array.from(selectEl.options).some(o => String(o.value) === String(id))) {
    const opt = new Option(text || String(id), id, true, true);
    selectEl.append(opt);
  }
  // Select it and notify Select2/DAL
  if ($sel) $sel.val(String(id)).trigger('change');
  else selectEl.value = String(id);
}

// Simple date conversion helpers
function localeDateToISO(dateStr) {
  // Convert common locale formats to ISO
  if (!dateStr) return '';
  
  // If already ISO format, return as-is
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) return dateStr;
  
  // Handle common European format (dd.mm.yyyy)
  const ddmmyyyy = /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/.exec(dateStr);
  if (ddmmyyyy) {
    return `${ddmmyyyy[3]}-${ddmmyyyy[2].padStart(2, '0')}-${ddmmyyyy[1].padStart(2, '0')}`;
  }
  
  // Handle US format (mm/dd/yyyy)
  const mmddyyyy = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(dateStr);
  if (mmddyyyy) {
    return `${mmddyyyy[3]}-${mmddyyyy[1].padStart(2, '0')}-${mmddyyyy[2].padStart(2, '0')}`;
  }
  
  return dateStr;
}

function isoToLocaleDate(isoDate) {
  // Convert ISO date to locale format for display
  if (!isoDate || !/^\d{4}-\d{2}-\d{2}$/.test(isoDate)) return isoDate;
  
  const [year, month, day] = isoDate.split('-');
  // Use simple European format as default (will be enhanced by Django localization)
  return `${day}.${month}.${year}`;
}

// Create season pass
function saveSeasonPass() {
  const type = document.querySelector('input[name="pass_type"]:checked').value;
  const modal = document.getElementById('addSeasonPassModal');
  const skiarea = document.getElementById('id_skiareaAdd')?.value || '';
  const network = document.getElementById('addNetworkSelect')?.value || '';
  const valid_from = localeDateToISO(document.getElementById('addValidFrom').value);
  const valid_until = localeDateToISO(document.getElementById('addValidUntil').value);

  const payload = {
    valid_from,
    valid_until,
    price_0: modal.querySelector('[name="priceAdd_0"]').value,
    price_1: modal.querySelector('[name="priceAdd_1"]').value,
  };
  if (type === 'skiarea') { payload.skiarea = skiarea || null; payload.skiarea_network = null; }
  else { payload.skiarea_network = network || null; payload.skiarea = null; }

  fetch(`/api/season-pass/`, {
    method: "POST",
    headers: {
      "X-CSRFToken": getCookie("csrftoken"),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  })
  .then(r => {
    if (!r.ok) throw new Error('Failed to create pass');
    // TODO: Handle successful response with toast/notification
    return null;
  })
  .then(() => location.reload())
  .catch(err => {
    console.error(err);
    alert("❌ Failed to create season pass.");
  });
}

// Update season pass
function updateSeasonPass() {
  const id = document.getElementById('editPassId').value;
  const modal = document.getElementById('editSeasonPassModal');
  const type = document.querySelector('input[name="edit_pass_type"]:checked').value;
  const skiarea = document.getElementById('id_skiareaEdit')?.value || '';
  const network = document.getElementById('editNetworkSelect')?.value || '';
  const valid_from = localeDateToISO(document.getElementById('editValidFrom').value);
  const valid_until = localeDateToISO(document.getElementById('editValidUntil').value);

  const payload = {
    valid_from, valid_until, 
    price_0: modal.querySelector('[name="priceEdit_0"]').value,
    price_1: modal.querySelector('[name="priceEdit_1"]').value,
    skiarea: (type === 'skiarea') ? (skiarea || null) : null,
    skiarea_network: (type === 'network') ? (network || null) : null,
  };

  fetch(`/api/season-pass/${id}/`, {
    method: "PATCH",
    headers: {
      "X-CSRFToken": getCookie("csrftoken"),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  })
  .then(r => {
    if (!r.ok) throw new Error('Failed to update pass');
    // TODO: Handle successful response with toast/notification
    return null;
  })
  .then(() => location.reload())
  .catch(err => {
    console.error(err);
    alert("❌ Failed to update season pass.");
  });
}

// Delete season pass via modal
function confirmDeleteSeasonPass() {
  const id = document.getElementById('deletePassId').value;
  fetch(`/api/season-pass/${id}/`, {
    method: "DELETE",
    headers: {
      "X-CSRFToken": getCookie("csrftoken"),
      "Content-Type": "application/json",
    },
  })
  .then(r => {
    if (!r.ok) throw new Error('Failed to delete pass');
    return null;
  })
  .then(() => location.reload())
  .catch(err => {
    console.error(err);
    alert("❌ Failed to delete season pass.");
  });
}

// DOM ready initialization
document.addEventListener('DOMContentLoaded', function() {
  // Wire radio buttons for type toggle
  document.addEventListener('change', function (e) {
    if (e.target && (e.target.id === 'addTypeSkiarea' || e.target.id === 'addTypeNetwork')) {
      toggleType('add', e.target.value);
    }
    if (e.target && (e.target.id === 'editTypeSkiarea' || e.target.id === 'editTypeNetwork')) {
      toggleType('edit', e.target.value);
    }
  });

  // Open & hydrate EDIT modal from data attributes
  const editModal = document.getElementById('editSeasonPassModal');
  editModal.addEventListener('show.bs.modal', function (event) {
    const btn = event.relatedTarget;
    const modal = event.target;
    const passId = btn.getAttribute('data-pass-id');
    const type = btn.getAttribute('data-pass-type');

    const skiareaId = btn.getAttribute('data-pass-skiarea-id');
    const skiareaName = btn.getAttribute('data-pass-skiarea-name');
    const networkId = btn.getAttribute('data-pass-network-id');
    const networkName = btn.getAttribute('data-pass-network-name');
    const validFrom = btn.getAttribute('data-pass-valid-from');
    const validUntil = btn.getAttribute('data-pass-valid-until');
    const amount   = btn.getAttribute('data-pass-price-amount')   || '';
    const currency = btn.getAttribute('data-pass-price-currency') || 'CHF';

    console.log("Editing pass", {passId, type, skiareaId, networkId, validFrom, validUntil, amount, currency});

    document.getElementById('editPassId').value = passId;

    // Type toggle + selects
    const typeRadioId = (type === 'network') ? 'editTypeNetwork' : 'editTypeSkiarea';
    document.getElementById(typeRadioId).checked = true;
    toggleType('edit', type);

    // Set selects if present
    const saSel = document.getElementById('editSkiareaSelect');
    const netSel = document.getElementById('editNetworkSelect');
    if (saSel) setSelect2Value(saSel, skiareaId, skiareaName);
    if (netSel) setSelect2Value(netSel, networkId, networkName);

    // Convert ISO dates to locale format for datepicker
    document.getElementById('editValidFrom').value = isoToLocaleDate(validFrom);
    document.getElementById('editValidUntil').value = isoToLocaleDate(validUntil);

    modal.querySelector('[name="priceEdit_0"]').value = amount;
    modal.querySelector('[name="priceEdit_1"]').value = currency;

    // Re-init datepicker views with correct format
    setTimeout(() => {
      $('#editValidFrom').datepicker('update');
      $('#editValidUntil').datepicker('update');
    });
  });

  // Open & hydrate DELETE modal
  const deleteModal = document.getElementById('deleteSeasonPassModal');
  deleteModal.addEventListener('show.bs.modal', function (event) {
    const btn = event.relatedTarget;
    const passId = btn.getAttribute('data-pass-id');
    const passName = btn.getAttribute('data-pass-name');
    document.getElementById('deletePassId').value = passId;
    document.getElementById('deletePassName').textContent = passName;
  });

  // Simple datepicker initialization for modals
  $('#addSeasonPassModal, #editSeasonPassModal').on('shown.bs.modal', function () {
    $(this).find('.datepicker').datepicker({
      format: "dd.mm.yyyy",
      todayHighlight: true,
      autoclose: true,
      weekStart: 1,
    });
  });

  // Auto-focus search for select2 dropdowns
  $(document).on('select2:open', () => {
    let searchField = document.querySelector('.select2-container--open .select2-search__field');
    if (searchField) searchField.focus();
  });
});