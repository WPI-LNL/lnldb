/* Funding request line items: add and remove rows without a round trip.

   Django formsets are index-based -- every field is named `<prefix>-<n>-<field>`
   and the management form's TOTAL_FORMS says how many to read back. So adding a
   row means cloning one, renumbering it, and bumping that count; removing one
   means dropping it and renumbering everything after it. */
(function ($) {
    'use strict';

    var $form = $('#fin-fr-form');
    var $table = $('#fin-fr-lines');
    if (!$form.length || !$table.length) { return; }

    var $total = $form.find('input[name$="-TOTAL_FORMS"]').first();
    if (!$total.length) { return; }

    // e.g. "line_items-TOTAL_FORMS" -> "line_items"
    var prefix = $total.attr('name').replace(/-TOTAL_FORMS$/, '');
    var indexPattern = new RegExp('(' + prefix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '-)\\d+(-)');

    function rows() {
        return $table.find('tbody tr.fin-fr-row');
    }

    /* Rewrite every name/id/for so the indexes run 0..n-1 with no gaps.
       Django ignores forms outside that range, so a gap silently drops data. */
    function renumber() {
        rows().each(function (index) {
            $(this).find('input, select, textarea, label').each(function () {
                var $el = $(this);
                ['name', 'id', 'for'].forEach(function (attr) {
                    var value = $el.attr(attr);
                    if (value && indexPattern.test(value)) {
                        $el.attr(attr, value.replace(indexPattern, '$1' + index + '$2'));
                    }
                });
            });
        });
        $total.val(rows().length);
    }

    $('#fin-fr-add').on('click', function () {
        var $last = rows().last();
        if (!$last.length) { return; }

        var $clone = $last.clone();

        $clone.find('input, select, textarea').each(function () {
            var $el = $(this);
            var type = ($el.attr('type') || '').toLowerCase();

            // A cloned row is a brand-new line: it must not carry the original's
            // primary key, or saving would overwrite that row instead.
            if ($el.attr('name') && /-id$/.test($el.attr('name'))) {
                $el.val('');
            } else if (type === 'checkbox' || type === 'radio') {
                $el.prop('checked', false);
            } else if ($el.is('select')) {
                $el.prop('selectedIndex', 0);
            } else if (type !== 'hidden') {
                $el.val('');
            }
        });

        // A clone is a brand-new line, so it carries no DELETE flag -- it is
        // removed from the DOM rather than marked for deletion.
        $clone.removeClass('fin-fr-deleted');
        $clone.find('td.fin-fr-remove').html(
            '<button type="button" class="btn btn-xs btn-link text-danger fin-fr-drop" ' +
            'title="Remove this line">&times;</button>');

        $table.find('tbody').append($clone);
        renumber();
        $clone.find('input[name$="-name"]').trigger('focus');
    });

    $table.on('click', '.fin-fr-drop', function () {
        var $row = $(this).closest('tr.fin-fr-row');
        var $flag = $row.find('.fin-fr-delete-flag input[type="checkbox"]');

        /* A line that is already in the database is staged for removal rather
           than deleted on the spot: Django deletes it when the form is saved,
           and until then the click stays undoable. */
        if ($flag.length) {
            var staged = !$flag.prop('checked');
            $flag.prop('checked', staged);
            $row.toggleClass('fin-fr-deleted', staged);
            $(this).attr('title', staged ? 'Keep this line' : 'Remove this line')
                   .html(staged ? '&#8634;' : '&times;');
            return;
        }

        // Keep one row on screen so there is always something to clone.
        if (rows().length <= 1) {
            $row.find('input, textarea').val('');
            $row.find('select').prop('selectedIndex', 0);
            return;
        }
        $row.next('tr.fin-fr-errors').remove();
        $row.remove();
        renumber();
    });
})(jQuery);
