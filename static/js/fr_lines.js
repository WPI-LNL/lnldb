/* The funding request and budget form: add and remove lines and a budget's
   categories without a round trip, and keep the form in step with its Type.

   Django formsets are index-based -- every field is named `<prefix>-<n>-<field>`
   and the management form's TOTAL_FORMS says how many to read back. Adding a
   row clones the empty row in a <template>, gives it the next free number and
   bumps that count. Numbers are never handed out again or closed up: a row
   removed from the page leaves a gap, which Django reads as a blank form and
   skips. Renumbering would be wrong here, because rows move between
   categories and a saved line's number has to stay below the count of saved
   ones.

   A budget's lines sit in one <tbody> per category, under its heading row.
   Where a row sits is the truth: when the form is sent, each line is given
   the key of the category it is under and its place there, and each category
   its place among the others. A category added here has no pk yet, so it is
   keyed new-<n>, and the server saves the categories before the lines.

   The Type decides what is on screen: the form carries is-budget or
   is-request, and CSS puts away whatever does not apply. A budget's name
   follows the fiscal year box, as the server insists the two agree. */
(function ($) {
    'use strict';

    var $form = $('#fin-fr-form');
    var $table = $('#fin-fr-lines');
    if (!$form.length || !$table.length) { return; }

    var $lineTotal = $form.find('input[name="line_items-TOTAL_FORMS"]');
    var $categoryTotal = $form.find('input[name="budget_categories-TOTAL_FORMS"]');
    var lineTemplate = $('#fin-line-template').html() || '';
    var categoryTemplate = $('#fin-category-template').html() || '';

    var $kind = $form.find('input[name="kind"]');
    var $name = $form.find('input[name="name"]');
    var $year = $form.find('select[name="fiscal_year"]');
    var fyPattern = /\bFY\s*(\d{4}|\d{2})\b/i;

    function isBudget() {
        var $checked = $kind.filter(':checked');
        return $checked.length ? $checked.val() === 'budget' : $form.hasClass('is-budget');
    }

    function blocks() { return $table.children('tbody.fin-cat-block'); }
    function looseBlock() { return blocks().filter('.is-loose'); }
    function categoryBlocks() { return blocks().not('.is-loose').not('.is-removed'); }
    function keyOf($block) { return $block.attr('data-key') || ''; }

    function categoryName($block) {
        return $.trim($block.find('input.fin-category-name').val()) || '(unnamed category)';
    }

    /* The next free number in a formset, taken and counted. */
    function take($total) {
        var index = parseInt($total.val(), 10) || 0;
        $total.val(index + 1);
        return index;
    }

    /* ---- Moving a line to another category -------------------------------- */
    /* Every line's Move to box lists the categories, its own selected. Rebuilt
       when a category comes or goes; a rename only relabels. */
    function refreshMoves() {
        var options = [];
        categoryBlocks().each(function () {
            options.push([keyOf($(this)), categoryName($(this))]);
        });
        options.push(['', 'No category']);
        $table.find('select.fin-line-move').each(function () {
            var $select = $(this);
            var here = keyOf($select.closest('tbody.fin-cat-block'));
            $select.empty();
            $.each(options, function (_, option) {
                $('<option>').val(option[0]).text(option[1])
                    .prop('selected', option[0] === here).appendTo($select);
            });
        });
    }

    $table.on('change', 'select.fin-line-move', function () {
        var wanted = $(this).val() || '';
        var $row = $(this).closest('tr.fin-fr-row');
        var $target = blocks().not('.is-removed').filter(function () {
            return keyOf($(this)) === wanted;
        }).first();
        if (!$target.length) { return; }
        $target.append($row, $row.next('tr.fin-fr-errors'));
        $row.addClass('fin-inherited-flash');
        window.setTimeout(function () { $row.removeClass('fin-inherited-flash'); }, 900);
    });

    /* ---- Lines -------------------------------------------------------------- */
    function addLine($block) {
        var index = take($lineTotal);
        var $row = $($.parseHTML($.trim(lineTemplate.replace(/__prefix__/g, index)))).filter('tr');
        $block.append($row);
        refreshMoves();
        $row.find(isBudget() ? 'input[name$="-number"]' : 'input[name$="-name"]').trigger('focus');
    }

    $('#fin-fr-add').on('click', function () { addLine(looseBlock()); });
    $table.on('click', '.fin-cat-add-line', function () {
        addLine($(this).closest('tbody.fin-cat-block'));
    });

    /* Under each Approved box, what it means as it stands: blank is Pending SGA
       Approval, 0 is Denied, an amount needs no tag. */
    $table.on('input change', 'input[name$="-amount_awarded"]', function () {
        var raw = $.trim($(this).val());
        var number = parseFloat(raw);
        var state = raw === '' ? 'pending' : (number === 0 ? 'denied' : '');
        var $tags = $(this).closest('td').find('.fin-approval-state');
        $tags.find('.is-waiting').prop('hidden', state !== 'pending');
        $tags.find('.is-turned-down').prop('hidden', state !== 'denied');
    });

    /* ---- Categories ----------------------------------------------------------- */
    $('#fin-category-add').on('click', function () {
        var index = take($categoryTotal);
        var key = 'new-' + index;
        var $block = $($.parseHTML($.trim(categoryTemplate.replace(/__prefix__/g, index))))
            .filter('tbody');
        $block.attr('data-key', key);
        $block.find('input[name$="-key"]').val(key);
        looseBlock().before($block);
        refreshMoves();
        $block.find('input.fin-category-name').trigger('focus');
    });

    /* Removing a category keeps its lines: they move to No category. A saved
       category is deleted when the form is saved; a new one just goes. */
    $table.on('click', '.fin-cat-remove', function () {
        var $block = $(this).closest('tbody.fin-cat-block');
        looseBlock().append($block.children('tr.fin-fr-row, tr.fin-fr-errors'));
        var saved = $block.find('input[name^="budget_categories-"][name$="-id"]').val();
        if (saved) {
            $block.find('.fin-cat-delete input[type="checkbox"]').prop('checked', true);
            $block.addClass('is-removed').hide();
        } else {
            $block.remove();
        }
        refreshMoves();
    });

    $table.on('input', 'input.fin-category-name', function () {
        var $block = $(this).closest('tbody.fin-cat-block');
        var key = keyOf($block);
        $table.find('select.fin-line-move option').filter(function () {
            return $(this).val() === key;
        }).text(categoryName($block));
    });

    /* ---- Sending the form ----------------------------------------------------- */
    /* Write down where everything sits. A request's lines keep the order typed
       in their Order boxes and have no category. */
    $form.on('submit', function () {
        if (!isBudget()) {
            $table.find('input[name$="-category_key"]').val('');
            return;
        }
        var place = 0;
        blocks().each(function () {
            var $block = $(this);
            var key = keyOf($block);
            if (!$block.hasClass('is-loose') && !$block.hasClass('is-removed')) {
                $block.find('input[name^="budget_categories-"][name$="-sort_order"]').val(place);
                place += 1;
            }
            $block.children('tr.fin-fr-row').each(function (order) {
                $(this).find('input[name$="-category_key"]').val(key);
                $(this).find('input[name^="line_items-"][name$="-sort_order"]').val(order);
            });
        });
    });

    /* ---- The Type ------------------------------------------------------------- */
    function shortYear() {
        return String($year.val() || '').slice(-2);
    }

    /* A budget is named for its year. An empty name gets "FY27 SGA Budget";
       a name with a year in it has that year changed; anything else is left
       for the Treasurer, and the server says if it does not name the year. */
    function nameForYear() {
        if (!isBudget() || !$name.length || !shortYear()) { return; }
        var name = $name.val();
        if (!name) {
            $name.val('FY' + shortYear() + ' SGA Budget');
        } else if (fyPattern.test(name)) {
            $name.val(name.replace(fyPattern, 'FY' + shortYear()));
        }
    }

    $kind.on('change', function () {
        var budget = isBudget();
        $form.toggleClass('is-budget', budget).toggleClass('is-request', !budget);
        nameForYear();
    });
    $year.on('change', nameForYear);

    refreshMoves();
})(jQuery);
