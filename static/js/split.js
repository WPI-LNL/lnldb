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

    /* Amounts are typed unsigned, as they read on the receipt: the bank line
       says which way the money went, and the server gives every slice its
       sign (SplitLineForm.clean_amount). So everything here is a magnitude,
       and a minus typed out of habit counts the same. */
    var targetCents = Math.abs(cents($remainder.data('target')));

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
            total += Math.abs(cents($(this).val()));
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
            $hint.text('Enter at least one entry.').removeClass('text-success text-danger');
        } else {
            $hint.text(money(Math.abs(remainder)) +
                       (remainder < 0 ? ' more than the line.' : ' left to settle.'))
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

        // Re-index every name/id from -(count-1) to -count. Every element, not
        // only the inputs: the event picker keeps its wrapper and the box that
        // shows the chosen event in a <span> and a <div> it finds by id, so a
        // copy left with the old ids would write its choice into the row it
        // was copied from.
        $clone.find('[id], [name]').each(function () {
            var $el = $(this);
            ['name', 'id'].forEach(function (attr) {
                var value = $el.attr(attr);
                if (!value) { return; }
                $el.attr(attr, value.replace(/-\d+-/, '-' + count + '-'));
            });
        });
        $clone.find('input, select, textarea').each(function () {
            var $el = $(this);
            if ($el.attr('type') === 'checkbox') {
                $el.prop('checked', false);
            } else if ($el.is('select')) {
                $el.prop('selectedIndex', 0);
            } else {
                $el.val('');
            }
        });
        // The event chosen on the copied row is display, not a value, so
        // clearing the inputs leaves it showing on the new row.
        $clone.find('.results_on_deck').empty();
        $clone.find('details').prop('open', false);

        $clone.appendTo('#fin-split-table tbody');
        $total.val(count + 1);
        // A copied picker is inert -- ajax_select.js wires each one up once,
        // and jQuery's clone() does not carry that over. This re-runs it for
        // whatever is new on the page.
        $(window).trigger('init-autocomplete');
        // Let routing.js wire up the row just added -- hide its FR pickers,
        // give its line picker back any lines the copied row had narrowed
        // away, and the rest of its routing rules.
        $(document).trigger('fin:rows-added', [$clone, $template]);
        recalc();
    });

    recalc();
})(jQuery);
