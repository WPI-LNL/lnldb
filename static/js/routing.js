/* How the routing fields react to each other on any allocation form.

   Three rules. The first two are about not making the Treasurer type something
   the database already knows; the third is about asking only when it matters:

     1. The funding request picker only appears when the chosen fund draws on
        one. Which funds those are is a flag on the FundSource row, rendered
        onto the <option> as data-requires-fr, so adding a fund in the admin
        needs no change here.

     2. Choosing a funding request line fills in the spend category and project
        that line was awarded for. Those were recorded when the award was
        entered; asking for them again on every transaction charged to the line
        is exactly the double data entry this module exists to remove.

     3. The "why is this leaving 315-AG" box appears only once the Projection
        tick box actually disagrees with the account the money came out of.
        Crossing the partition is legitimate -- LNL buys Projection gear from
        the main account and SGA reimburses it -- so the question is asked at
        the moment it becomes relevant rather than sitting on screen always.

   The server enforces rules 1 and 3 either way (ParsedTransaction.clean() and
   BaseAllocationForm._check_fund_and_fr_line). None of this is validation. */
(function ($) {
    'use strict';

    /* The controls live in different wrappers on each page: a crispy
       form-group on the entry page, a plain one in the queue and the split
       modal. Walking up to the nearest wrapper keeps this page-agnostic. */
    function container($field) {
        var $wrap = $field.closest('.form-group');
        return $wrap.length ? $wrap : $field.parent();
    }

    /* One allocation form's routing fields. In the queue every row is its own
       <form>; in the split modal each row shares one, so fields are matched by
       name suffix within the nearest common ancestor. */
    function scopeOf($field) {
        var $row = $field.closest('tr');
        if ($row.length) { return $row; }
        var $form = $field.closest('form');
        return $form.length ? $form : $(document);
    }

    function fields($any) {
        var $scope = scopeOf($any);
        return {
            fund: $scope.find('[name$="fund_source"]').first(),
            line: $scope.find('[name$="fr_line_target"]').first(),
            cross: $scope.find('[name$="allow_cross_year_fr"]').first(),
            category: $scope.find('[name$="lnl_spend_category"]').first(),
            project: $scope.find('[name$="project_tag"]').first(),
            projection: $scope.find('[name$="is_projection"]').first(),
            reason: $scope.find('.fin-partition-reason').first()
        };
    }

    /* ---- 1. Show the FR picker only when the fund needs one --------------- */
    function gate($fund) {
        var f = fields($fund);
        if (!f.line.length) { return; }

        var required = f.fund.find('option:selected').attr('data-requires-fr') === '1';
        container(f.line).toggle(required);
        if (f.cross.length) { container(f.cross).toggle(required); }

        if (!required && f.line.val()) {
            // A stale line would be rejected on save, with the error landing on
            // a field that is no longer on screen.
            f.line.val('').trigger('change');
            if (f.cross.length) { f.cross.prop('checked', false); }
        }
    }

    /* ---- 2. Inherit the line's expected routing --------------------------- */

    /* Only ever overwrite a box this script filled in itself. A value the
       Treasurer chose by hand survives switching between FR lines; one that
       was inherited follows along. */
    function adopt($target, value) {
        if (!$target.length || !$target.is('select')) { return; }

        var inherited = $target.data('fin-inherited');
        var current = $target.val();
        var untouched = !current || (inherited !== undefined && String(inherited) === String(current));
        if (!untouched) { return; }

        if (value) {
            if (!$target.find('option[value="' + value + '"]').length) { return; }
            $target.val(value);
            $target.data('fin-inherited', value);
        } else if (inherited !== undefined) {
            // The new line specifies nothing, so clear what the old one lent.
            $target.val('');
            $target.removeData('fin-inherited');
        }
        $target.trigger('change.fin-inherit');
        $target.closest('.form-group, td').addClass('fin-inherited-flash');
        window.setTimeout(function () {
            $target.closest('.form-group, td').removeClass('fin-inherited-flash');
        }, 900);
    }

    function inherit($line) {
        var f = fields($line);
        var $option = $line.find('option:selected');
        adopt(f.category, $option.attr('data-spend-category') || '');
        adopt(f.project, $option.attr('data-project-tag') || '');
    }

    /* A hand-edit of either target releases it from inheritance. Namespaced
       'change.fin-inherit' above is excluded so adopt() does not undo itself. */
    function watchManualEdits($any) {
        var f = fields($any);
        $.each([f.category, f.project], function (_, $target) {
            if (!$target.length || $target.data('fin-watched')) { return; }
            $target.data('fin-watched', true);
            $target.on('change', function (event) {
                if (event.namespace === 'fin-inherit') { return; }
                $target.removeData('fin-inherited');
            });
        });
    }

    /* ---- 3. Ask for a reason only when the partition is actually crossed -- */
    function partitionReason($any) {
        var f = fields($any);
        if (!f.reason.length || !f.projection.length) { return; }

        // Rendered by the template from the org code on the bank line.
        var startsProjection = f.reason.attr('data-default-projection') === '1';
        var crossed = f.projection.is(':checked') !== startsProjection;
        f.reason.toggleClass('is-needed', crossed);
        // The box lives in the folded half of the row, so asking for it has to
        // open that half or the question is invisible.
        if (crossed) {
            f.reason.closest('.fin-queue-row').find('.fin-fields-more').removeClass('is-folded');
        }
    }

    function bind(root) {
        $(root).find('.fin-partition-reason').each(function () {
            var $reason = $(this);
            if ($reason.data('fin-partition')) { return; }
            $reason.data('fin-partition', true);
            var f = fields($reason);
            if (!f.projection.length) { return; }
            f.projection.on('change', function () { partitionReason($reason); });
            partitionReason($reason);
        });

        $(root).find('select.fin-fund-source, select[name$="fund_source"]').each(function () {
            var $fund = $(this);
            if ($fund.data('fin-gate')) { return; }
            $fund.data('fin-gate', true);
            $fund.on('change', function () { gate($fund); });
            gate($fund);
        });

        $(root).find('select[name$="fr_line_target"]').each(function () {
            var $line = $(this);
            if ($line.data('fin-inherit')) { return; }
            $line.data('fin-inherit', true);
            watchManualEdits($line);
            $line.on('change', function () { inherit($line); });
        });
    }

    $(function () { bind(document); });

    // The split modal and the queue both add rows after load.
    $(document).on('fin:rows-added', function (event, root) { bind(root || document); });
})(jQuery);
