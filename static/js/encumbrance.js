/* The encumbrance page: "Add a line", and the running total of the lines. */
(function ($) {
    'use strict';

    var $form = $('#fin-encumbrance-form');
    if (!$form.length) { return; }

    var $total = $('#fin-encumbrance-total');

    /* Integer cents, as in split.js: 0.1 + 0.2 must add up. Amounts are typed
       unsigned and the server makes them money going out. */
    function cents(value) {
        var n = parseFloat(value);
        return isNaN(n) ? 0 : Math.abs(Math.round(n * 100));
    }

    function recalc() {
        var sum = 0;
        $form.find('.fin-line-amount').each(function () {
            var $del = $(this).closest('tr').find('input[name$="-DELETE"]');
            if ($del.length && $del.is(':checked')) { return; }
            sum += cents($(this).val());
        });
        $total.text('$' + (sum / 100).toLocaleString(undefined, {
            minimumFractionDigits: 2, maximumFractionDigits: 2
        }));
    }

    $form.on('input change', '.fin-line-amount, input[name$="-DELETE"]', recalc);

    /* A new line is the formset's empty form with __prefix__ replaced by the
       next index -- every id and name, so the event picker's own <span> and
       <div> belong to the new row and not to a copy of another. */
    $('#fin-add-line').on('click', function () {
        var $count = $form.find('input[name$="-TOTAL_FORMS"]').first();
        var index = parseInt($count.val(), 10);
        var html = $('#fin-encumbrance-empty').html().replace(/__prefix__/g, index);
        var $row = $(html).filter('tr.fin-encumbrance-line');
        $row.appendTo('#fin-encumbrance-lines tbody');
        $count.val(index + 1);
        // ajax_select.js wires each picker up once, on load or on this event.
        $(window).trigger('init-autocomplete');
        // routing.js: hide the FR pickers until a fund needs them, and the rest.
        $(document).trigger('fin:rows-added', [$row]);
        recalc();
    });

    recalc();
})(jQuery);
