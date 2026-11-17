(function () {
  const body = document.body;
  const versionUrl = body.dataset.versionUrl;
  if (!versionUrl) return;

  const tabIdKey = 'erp-tab-id';
  let tabId = sessionStorage.getItem(tabIdKey);
  if (!tabId) {
    tabId = (window.crypto && crypto.randomUUID)
      ? crypto.randomUUID()
      : Date.now().toString(36) + Math.random().toString(36).slice(2);
    sessionStorage.setItem(tabIdKey, tabId);
  }

  const forms = [];
  let restoring = false;
  let submissionPending = false;
  let checkingForChanges = false;
  const draftVersion = 2;
  const draftLifetimeMs = 7 * 24 * 60 * 60 * 1000;
  const noticeId = 'tab-sync-notice';
  const pendingSubmitKey = 'erp-pending-form-submit';

  try {
    Object.keys(localStorage).forEach(function (key) {
      if (!key.startsWith('erp-form-draft:')) return;
      try {
        const draft = JSON.parse(localStorage.getItem(key));
        if (!draft || draft.version !== draftVersion ||
            !Number.isFinite(draft.savedAt) ||
            Date.now() - draft.savedAt > draftLifetimeMs) {
          localStorage.removeItem(key);
        }
      } catch (error) {
        console.error('Unable to check an old form draft.', error);
        localStorage.removeItem(key);
      }
    });
  } catch (error) {
    console.error('Unable to inspect saved form drafts in browser storage.', error);
  }

  function showNotice(message, warning, draftKey) {
    let notice = document.getElementById(noticeId);
    if (!notice) {
      notice = document.createElement('div');
      notice.id = noticeId;
      notice.className = 'alert alert-dismissible fade show no-print';
      notice.setAttribute('role', 'status');
      const container = document.querySelector('body > .container-fluid.px-4');
      if (!container) return;
      container.prepend(notice);
    }

    notice.classList.toggle('alert-warning', !!warning);
    notice.classList.toggle('alert-info', !warning);
    notice.replaceChildren(document.createTextNode(message + ' '));

    if (draftKey) {
      const discard = document.createElement('button');
      discard.type = 'button';
      discard.className = 'btn btn-sm btn-outline-secondary ms-2';
      discard.textContent = 'Discard draft';
      discard.addEventListener('click', function () {
        localStorage.removeItem(draftKey);
        const state = forms.find(item => item.key === draftKey);
        if (state) state.dirty = false;
        notice.remove();
      });
      notice.appendChild(discard);
    }
  }

  function editableControls(form) {
    return Array.from(form.elements).filter(function (element) {
      if (!element || element.readOnly ||
          (element.disabled && element.tagName !== 'SELECT')) return false;
      if (!['INPUT', 'SELECT', 'TEXTAREA'].includes(element.tagName)) return false;
      if (element.classList.contains('searchable-select-input')) return false;
      if (['hidden', 'password', 'file', 'submit', 'button', 'reset'].includes(element.type)) return false;
      if (element.name === 'csrf_token') return false;
      return true;
    });
  }

  function getFormKey(form, index) {
    const identity = form.id || form.getAttribute('name') || index;
    return 'erp-form-draft:' + tabId + ':' +
      encodeURIComponent(location.pathname + location.search + '|' + form.action + '|' + identity);
  }

  function readControl(element) {
    if (element.tagName === 'SELECT' && element.multiple) {
      return { kind: 'multiple', value: Array.from(element.selectedOptions, option => option.value) };
    }
    if (element.type === 'checkbox' || element.type === 'radio') {
      return { kind: 'checked', value: element.checked };
    }
    return { kind: 'value', value: element.value };
  }

  function controlKeys(controls) {
    const occurrences = new Map();
    return controls.map(function (element, index) {
      let identity = element.name;
      if (!identity) {
        const row = element.closest('tr');
        const table = row && row.closest('table');
        if (row && table) {
          identity = table.id + ':row:' + Array.from(table.rows).indexOf(row) +
            ':cell:' + Array.from(row.cells).indexOf(element.closest('td')) +
            ':' + element.type + ':' + element.className;
        } else {
          identity = element.id || 'control:' + index;
        }
      }

      const occurrence = occurrences.get(identity) || 0;
      occurrences.set(identity, occurrence + 1);
      return identity + ':' + occurrence;
    });
  }

  function snapshotForm(form) {
    const tables = {};
    form.querySelectorAll('table[id]').forEach(function (table) {
      tables[table.id] = {
        rows: table.querySelectorAll('tbody tr').length,
        columns: table.querySelectorAll('thead input').length
      };
    });
    const controls = editableControls(form);
    const keys = controlKeys(controls);
    return {
      version: draftVersion,
      savedAt: Date.now(),
      tables: tables,
      extraChargeRows: form.querySelectorAll('#extraCharges > div').length,
      controls: Object.fromEntries(controls.map(function (control, index) {
        return [keys[index], readControl(control)];
      }))
    };
  }

  function saveDraft(state) {
    if (!state.dirty) return true;
    try {
      localStorage.setItem(state.key, JSON.stringify(snapshotForm(state.form)));
      state.saved = true;
      return true;
    } catch (error) {
      state.saved = false;
      console.error('Unable to save this form draft in browser storage.', error);
      showNotice('This browser could not save your draft. Automatic page refresh is paused to protect your unsaved changes.', true);
      return false;
    }
  }

  function resizeDynamicRows(form, draft) {
    const addButtons = {
      itemsTable: '#addRow',
      brandDiscountTable: '#addBrandRow',
      categoryDiscountTable: '#addCategoryRow',
      gridTable: '#addRow'
    };
    Object.entries(draft.tables || {}).forEach(function ([tableId, dimensions]) {
      const table = form.querySelector('#' + tableId);
      const addRowSelector = addButtons[tableId];
      const addRow = addRowSelector ? form.querySelector(addRowSelector) : null;
      if (!table) return;

      const rowCount = () => table.querySelectorAll('tbody tr').length;
      while (addRow && rowCount() < dimensions.rows) addRow.click();
      while (rowCount() > dimensions.rows) {
        const remove = table.querySelector('tbody tr:last-child .remove-row');
        if (!remove) break;
        remove.click();
      }

      if (tableId === 'gridTable') {
        const addColumn = form.querySelector('#addColumn');
        const columnCount = () => table.querySelectorAll('thead input[name="column[]"]').length;
        while (addColumn && columnCount() < dimensions.columns) addColumn.click();
        while (columnCount() > dimensions.columns) {
          const headerRow = table.tHead.rows[0];
          const remove = headerRow.cells[headerRow.cells.length - 2].querySelector('.remove-col');
          if (!remove) break;
          remove.click();
        }
      }
    });

    const chargeRows = form.querySelector('#extraCharges');
    const addCharge = form.querySelector('#addCharge');
    if (chargeRows && addCharge) {
      while (chargeRows.children.length < draft.extraChargeRows) addCharge.click();
      while (chargeRows.children.length > draft.extraChargeRows) {
        const remove = chargeRows.lastElementChild.querySelector('.remove-charge');
        if (!remove) break;
        remove.click();
      }
    }
  }

  function setControlValue(element, saved) {
    if (saved.kind === 'multiple') {
      const selectedValues = new Set(saved.value);
      Array.from(element.options).forEach(function (option) {
        option.selected = selectedValues.has(option.value);
      });
      if (element.refreshSearchable) element.refreshSearchable();
      return saved.value.every(function (value) {
        return Array.from(element.options).some(option => option.value === value);
      });
    }

    if (element.tagName === 'SELECT') {
      const optionExists = Array.from(element.options).some(option => option.value === saved.value);
      if (!optionExists) return false;
      element.value = saved.value;
      if (element.refreshSearchable) element.refreshSearchable();
      return true;
    }

    if (saved.kind === 'checked') {
      element.checked = saved.value;
      return true;
    }

    element.value = saved.value;
    return true;
  }

  function restoreDraft(state, draft) {
    resizeDynamicRows(state.form, draft);
    const controls = editableControls(state.form);
    const savedControls = draft.controls || {};
    const keys = controlKeys(controls);
    const savedByControl = new Map(controls.map(function (control, index) {
      return [control, savedControls[keys[index]]];
    }));
    let missingValues = false;
    restoring = true;

    controls.forEach(function (control, index) {
      if (control.name !== 'customer_id' && control.name !== 'mechanic_id') return;
      const saved = savedControls[keys[index]];
      if (saved && !setControlValue(control, saved)) missingValues = true;
    });

    controls.forEach(function (control, index) {
      const saved = savedControls[keys[index]];
      if (!saved || control.tagName !== 'SELECT' ||
          control.name === 'customer_id' || control.name === 'mechanic_id' ||
          control.name === 'purchase_item_id[]') return;
      if (!setControlValue(control, saved)) {
        missingValues = true;
        return;
      }
      control.dispatchEvent(new Event('change', { bubbles: true }));
    });

    controls.forEach(function (control) {
      if (control.tagName !== 'SELECT' || control.name !== 'purchase_item_id[]') return;
      const saved = savedByControl.get(control);
      if (!saved) return;
      if (!setControlValue(control, saved)) {
        if (saved.value) missingValues = true;
        return;
      }
      control.dispatchEvent(new Event('change', { bubbles: true }));
    });

    const customer = controls.find(control => control.name === 'customer_id');
    const mechanic = controls.find(control => control.name === 'mechanic_id');
    if (customer && mechanic) {
      const selectedContact = customer.value ? customer : mechanic;
      selectedContact.dispatchEvent(new Event('change', { bubbles: true }));
    }

    controls.forEach(function (control, index) {
      const saved = savedControls[keys[index]];
      if (!saved || control.tagName === 'SELECT') return;
      if (setControlValue(control, saved)) {
        control.dispatchEvent(new Event(saved.kind === 'checked' ? 'change' : 'input', { bubbles: true }));
      }
    });

    restoring = false;
    state.dirty = true;
    saveDraft(state);
    const detail = missingValues
      ? 'Some saved selections are no longer available; please review this draft.'
      : 'Your saved form draft was restored. Review it before saving.';
    showNotice(detail, missingValues, state.key);
  }

  function clearSuccessfulSubmission() {
    let pending;
    try {
      pending = JSON.parse(sessionStorage.getItem(pendingSubmitKey) || 'null');
    } catch (error) {
      console.error('Unable to read the pending form draft state.', error);
      sessionStorage.removeItem(pendingSubmitKey);
      return;
    }
    if (!pending) return;

    if (pending.method === 'get' || document.querySelector('.alert-success')) {
      pending.draftKeys.forEach(key => localStorage.removeItem(key));
    }
    sessionStorage.removeItem(pendingSubmitKey);
  }

  clearSuccessfulSubmission();

  document.querySelectorAll('form').forEach(function (form, index) {
    if (form.method.toLowerCase() === 'dialog') return;
    const controls = editableControls(form);
    if (!controls.length) return;

    const state = {
      form: form,
      key: getFormKey(form, index),
      dirty: false,
      saved: false,
      timer: null
    };
    forms.push(state);

    let rawDraft;
    try {
      rawDraft = localStorage.getItem(state.key);
    } catch (error) {
      console.error('Unable to read this form draft from browser storage.', error);
    }

    if (rawDraft) {
      try {
        const draft = JSON.parse(rawDraft);
        if (draft.version === draftVersion &&
            Date.now() - draft.savedAt <= draftLifetimeMs &&
            draft.controls && typeof draft.controls === 'object' &&
            !Array.isArray(draft.controls)) {
          restoreDraft(state, draft);
        } else {
          localStorage.removeItem(state.key);
        }
      } catch (error) {
        console.error('Unable to restore this saved form draft.', error);
        localStorage.removeItem(state.key);
      }
    }

    function scheduleSave() {
      if (restoring) return;
      state.dirty = true;
      state.saved = false;
      window.clearTimeout(state.timer);
      state.timer = window.setTimeout(function () {
        saveDraft(state);
      }, 200);
    }

    form.addEventListener('input', scheduleSave);
    form.addEventListener('change', scheduleSave);
    form.addEventListener('click', function (event) {
      if (event.target.closest('button[type="button"]')) scheduleSave();
    });
    form.addEventListener('submit', function () {
      window.clearTimeout(state.timer);
      saveDraft(state);
      submissionPending = true;
      try {
        sessionStorage.setItem(pendingSubmitKey, JSON.stringify({
          source: location.href,
          method: form.method.toLowerCase(),
          draftKeys: forms.filter(item => item.dirty).map(item => item.key)
        }));
      } catch (error) {
        console.error('Unable to track this form submission.', error);
      }
    });
  });

  function flushDrafts() {
    forms.forEach(function (state) {
      window.clearTimeout(state.timer);
      saveDraft(state);
    });
  }

  window.addEventListener('pagehide', flushDrafts);
  window.FormDrafts = {
    flush: flushDrafts,
    mustProtectUnsavedChanges: function () {
      return forms.some(state => state.dirty && !state.saved);
    }
  };

  let currentVersion = body.dataset.databaseVersion;
  let refreshDeferred = false;

  async function checkForDatabaseChanges() {
    if (document.visibilityState === 'hidden' || submissionPending || checkingForChanges) return;
    checkingForChanges = true;
    try {
      const response = await fetch(versionUrl, {
        cache: 'no-store',
        credentials: 'same-origin',
        headers: { Accept: 'application/json' }
      });
      if (response.redirected) {
        window.location.assign(response.url);
        return;
      }
      if (!response.ok) throw new Error('Data-version check returned HTTP ' + response.status);
      const result = await response.json();
      if (result.version === currentVersion) return;

      window.FormDrafts.flush();
      if (window.FormDrafts.mustProtectUnsavedChanges()) {
        if (!refreshDeferred) {
          showNotice('Another tab saved changes, but this browser could not save your draft. Refresh manually after copying your unsaved work.', true);
          refreshDeferred = true;
        }
        return;
      }
      window.location.reload();
    } catch (error) {
      console.error('Unable to check for changes saved in another tab.', error);
    } finally {
      checkingForChanges = false;
    }
  }

  window.setInterval(checkForDatabaseChanges, 4000);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') checkForDatabaseChanges();
  });
  window.addEventListener('pageshow', function () {
    submissionPending = false;
    checkForDatabaseChanges();
  });
})();
