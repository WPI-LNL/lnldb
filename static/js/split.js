/* Split-purchase modal: live remainder, and a Save button that stays disabled
   until the unallocated remainder is exactly $0.00. */
(function ($) {
    'use strict';

    var $form = $('#fin-split-form');
    if (!$form.length) { return; }

    var $remainder = $('#fin-remainder');
    var $save = $('#fin-split-save');
    var $hint = $('#fin-split-hint');
    /* Work in integer cents. Floating-point dollars would let 0.1 + 0.2 read as
       unbalanced, which is exactly the bug this control exists to prevent. */
    function cents(value) {
        var n = parseFloat(value);
        if (isNaN(n)) { return 0; }
        return Math.round(n * 100);
    }

    var targetCents = cents($remainder.data('target'));

    function money(c) {
        var sign = c < 0 ? '-' : '';
        var abs = Math.abs(c) / 100;
        return sign + '$' + abs.toLocaleString(undefined, {
            minimumFractionDigits: 2, maximumFractionDigits: 2
        });
    }

    function recalc() {
        var total = 0;
        $form.find('.split-amount').each(function () {
            var $row = $(this).closest('tr');
            var $del = $row.find('input[type="checkbox"][name$="-DELETE"]');
            if ($del.length && $del.is(':checked')) { return; }
            total += cents($(this).val());
        });

        var remainder = targetCents - total;
        var balanced = (remainder === 0) && (total !== 0);

        $remainder.text(money(remainder))
                  .toggleClass('is-balanced', balanced)
                  .toggleClass('is-unbalanced', !balanced);

        $save.prop('disabled', !balanced);

        if (balanced) {
            $hint.text('Balanced — ready to save.').removeClass('text-danger').addClass('text-success');
        } else if (total === 0) {
            $hint.text('Enter at least one allocation.').removeClass('text-success text-danger');
        } else {
            /* The bank line may be negative (an expense), so "over-allocated"
               is not simply "remainder < 0". A remainder pointing the same way
               as the target still needs allocating; one pointing the other way
               means the slices have overshot. */
            var overshot = (targetCents >= 0) ? (remainder < 0) : (remainder > 0);
            $hint.text(money(Math.abs(remainder)) +
                       (overshot ? ' over-allocated.' : ' still unallocated.'))
                 .removeClass('text-success').addClass('text-danger');
        }
    }

    $form.on('input change', '.split-amount, input[name$="-DELETE"]', recalc);

    /* ---- Add another slice by cloning the last row ------------------------- */
    $('#fin-add-split').on('click', function () {
        var $total = $('#id_slices-TOTAL_FORMS');
        if (!$total.length) {
            // Fall back to whatever prefix the formset actually rendered with.
            $total = $form.find('input[name$="-TOTAL_FORMS"]').first();
        }
        var count = parseInt($total.val(), 10);
        var $rows = $('#fin-split-table tbody tr.fin-split-row');
        var $template = $rows.last();
        var $clone = $template.clone();

        // Re-index every name/id from -(count-1) to -count.
        $clone.find('input, select, textarea').each(function () {
            var $el = $(this);
            ['name', 'id'].forEach(function (attr) {
                var value = $el.attr(attr);
                if (!value) { return; }
                $el.attr(attr, value.replace(/-\d+-/, '-' + count + '-'));
            });
            if ($el.attr('type') === 'checkbox') {
                $el.prop('checked', false);
            } else if ($el.is('select')) {
                $el.prop('selectedIndex', 0);
            } else {
                $el.val('');
            }
        });

        $clone.appendTo('#fin-split-table tbody');
        $total.val(count + 1);
        // Let fund_gate.js hide the FR picker on the row just added.
        $(document).trigger('fin:rows-added', [$clone]);
        recalc();
    });

    recalc();
})(jQuery);
