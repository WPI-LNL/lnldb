/* The X on a row of a line table: an encumbrance's lines, a split's entries, a
   funding request's or a budget's lines.

   Django deletes a row only if its DELETE box is ticked when the form is sent,
   so the box is still in the row, hidden (partials/_row_remove.html), and the X
   drives it. Ticking it through jQuery's change event keeps the running totals
   in split.js and encumbrance.js right.

   A saved row stays on screen, struck through, until the form is saved, and its
   X becomes an undo: nothing is gone yet, and losing a saved line to a slip of
   the mouse should cost one click. A row that was never saved has nothing to
   lose, so it goes at once. It is hidden, not taken out of the page: formset
   rows are numbered, and split.js copies the last row to make a new one. */
(function ($) {
    'use strict';

    var CROSS = '&times;';
    var UNDO = '<span class="glyphicon glyphicon-repeat" aria-hidden="true"></span>';

    function label($button, text) {
        $button.attr({title: text, 'aria-label': text});
    }

    function flagOf($row) {
        return $row.find('.fin-row-flag input[type="checkbox"]');
    }

    function stage($row, removed) {
        var $button = $row.find('.fin-row-drop');
        flagOf($row).prop('checked', removed).trigger('change');
        $row.toggleClass('fin-row-removed', removed);
        $button.html(removed ? UNDO : CROSS);
        label($button, removed ? 'Keep this line' : 'Remove this line');
    }

    function drop($row) {
        flagOf($row).prop('checked', true).trigger('change');
        $row.add($row.next('.fin-row-errors')).hide();
    }

    $(document).on('click', '.fin-row-drop', function () {
        var $row = $(this).closest('tr');
        if ($row.is('[data-saved]')) {
            stage($row, !flagOf($row).prop('checked'));
        } else {
            drop($row);
        }
    });

    /* split.js makes a new row by copying the last one, which may be a saved
       row, or one already removed. */
    $(document).on('fin:rows-added', function (event, $row) {
        $row.removeAttr('data-saved').removeClass('fin-row-removed').show();
        var $button = $row.find('.fin-row-drop').html(CROSS);
        label($button, 'Remove this line');
    });

    /* A form sent back with errors keeps its ticked boxes. */
    $(function () {
        $('.fin-row-flag input[type="checkbox"]:checked').each(function () {
            var $row = $(this).closest('tr');
            if ($row.is('[data-saved]')) {
                stage($row, true);
            } else {
                drop($row);
            }
        });
    });
})(jQuery);
