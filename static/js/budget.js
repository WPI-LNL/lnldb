/* A budget's page: open and close the entries folded under each line.

   The entries row starts folded (.is-folded). Without this script the
   <noscript> rule in base_finance.html shows every one of them, so nothing
   is ever out of reach. */
(function ($) {
    'use strict';

    var $table = $('#fin-budget-lines');
    if (!$table.length) { return; }

    function toggle($line) {
        var $entries = $table.find('tr.fin-budget-entries[data-line="' + $line.data('line') + '"]');
        var open = $entries.hasClass('is-folded');
        $entries.toggleClass('is-folded', !open);
        $line.toggleClass('is-open', open).attr('aria-expanded', open ? 'true' : 'false');
    }

    $table.on('click', 'tr.fin-budget-line', function (event) {
        // A link inside the row still goes where it points.
        if ($(event.target).closest('a').length) { return; }
        toggle($(this));
    });
    $table.on('keydown', 'tr.fin-budget-line', function (event) {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            toggle($(this));
        }
    });
})(jQuery);
