/* Spreadsheet ledger: column visibility, multi-select, bulk action bar.
   jQuery 1.10 / Bootstrap 3 -- no ES6, to match the rest of lnldb. */
(function ($) {
    'use strict';

    var STORAGE_KEY = 'lnl.finance.ledger.columns';

    /* ---- Column visibility ------------------------------------------------ */
    function applyColumns(hidden) {
        $('#fin-ledger-table [data-col]').each(function () {
            var col = $(this).data('col');
            $(this).toggle($.inArray(col, hidden) === -1);
        });
        $('.fin-col-check').each(function () {
            var col = $(this).data('col');
            $(this).prop('checked', $.inArray(col, hidden) === -1);
        });
    }

    function loadHidden() {
        try {
            var raw = window.localStorage.getItem(STORAGE_KEY);
            if (raw) { return JSON.parse(raw); }
        } catch (e) { /* localStorage unavailable; fall through to defaults */ }
        // Default: hide everything not marked default in LEDGER_COLUMNS.
        var hidden = [];
        $('.fin-col-check').each(function () {
            if (!$(this).is(':checked')) { hidden.push($(this).data('col')); }
        });
        return hidden;
    }

    function saveHidden(hidden) {
        try {
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(hidden));
        } catch (e) { /* non-fatal */ }
    }

    var hiddenCols = loadHidden();
    applyColumns(hiddenCols);

    $('#fin-column-picker').on('click', '.fin-col-toggle', function (e) {
        e.preventDefault();
        e.stopPropagation();  // keep the dropdown open while toggling
        var col = $(this).data('col');
        var index = $.inArray(col, hiddenCols);
        if (index === -1) { hiddenCols.push(col); } else { hiddenCols.splice(index, 1); }
        saveHidden(hiddenCols);
        applyColumns(hiddenCols);
    });

    $('#fin-col-reset').on('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        try { window.localStorage.removeItem(STORAGE_KEY); } catch (err) { /* non-fatal */ }
        window.location.reload();
    });

    /* ---- Multi-select ----------------------------------------------------- */
    var $bar = $('#fin-bulk-bar');
    var $count = $('#fin-bulk-count');
    var $selected = $('#fin-bulk-selected');
    var lastChecked = null;

    function selectedIds() {
        return $('.fin-row-check:checked').map(function () { return this.value; }).get();
    }

    function refresh() {
        var ids = selectedIds();
        $count.text(ids.length);
        $selected.val(ids.join(','));
        $bar.toggleClass('is-visible', ids.length > 0);
        $('.fin-row-check').each(function () {
            $(this).closest('tr').toggleClass('fin-row-selected', this.checked);
        });
        var total = $('.fin-row-check').length;
        $('#fin-select-all').prop('checked', total > 0 && ids.length === total);
    }

    $('#fin-select-all').on('change', function () {
        $('.fin-row-check').prop('checked', this.checked);
        refresh();
    });

    $('.fin-row-check').on('click', function (e) {
        // Shift-click selects a contiguous range, like a real spreadsheet.
        if (e.shiftKey && lastChecked && lastChecked !== this) {
            var boxes = $('.fin-row-check');
            var start = boxes.index(lastChecked);
            var end = boxes.index(this);
            var checked = this.checked;
            boxes.slice(Math.min(start, end), Math.max(start, end) + 1)
                 .prop('checked', checked);
        }
        lastChecked = this;
        refresh();
    });

    $('#fin-bulk-cancel').on('click', function () {
        $('.fin-row-check, #fin-select-all').prop('checked', false);
        refresh();
    });

    /* ---- Bulk action: show only the relevant value picker ------------------ */
    function syncBulkValue() {
        var action = $('#fin-bulk-action').val();
        $('.fin-bulk-value').each(function () {
            $(this).toggle($(this).data('for') === action);
        });
    }

    $('#fin-bulk-action').on('change', syncBulkValue);
    syncBulkValue();

    $('#fin-bulk-form').on('submit', function () {
        $selected.val(selectedIds().join(','));
    });

    refresh();
})(jQuery);
