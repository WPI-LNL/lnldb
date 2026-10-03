/* How the routing fields react to each other on any allocation form.

   Five rules. The first two and the fifth are about not making the Treasurer
   type something the database already knows; the third is about asking only
   when it matters; the fourth is about not asking two questions where only one
   can be answered:

     1. The funding request pickers only appear when the chosen fund draws on
        funding requests: the line on spending, and the request itself on
        SGA's own payments -- a reimbursement in, money SGA took back out.
        Which funds those are is a flag on the FundSource row, rendered onto
        the <option> as data-requires-fr, so adding a fund in the admin needs
        no change here.

     2. Choosing a funding request line fills in the spend category and project
        that line was awarded for. Those were recorded when the award was
        entered; asking for them again on every transaction charged to the line
        is exactly the double data entry this module exists to remove.

        The queue usually gets there first: LNL's Workday memos name the
        request line outright -- "Velcro restock, consumables, (A.27.16)" -- so
        the server picks the line and its category before the page is rendered
        (finance/suggestions.py). What it renders then is a box already filled
        in and carrying data-fin-inherited, which is what tells adopt() below
        that the value is on loan from the line rather than chosen by hand, and
        so must follow along if the Treasurer picks a different line.

     3. The "why is this leaving 315-AG" box appears only once the Projection
        tick box actually disagrees with the account the money came out of.
        Crossing the partition is legitimate -- LNL buys Projection gear from
        the main account and SGA reimburses it -- so the question is asked at
        the moment it becomes relevant rather than sitting on screen always.

     4. Naming the purchase a credit reverses puts the revenue boxes away --
        the event and the revenue type, and in the queue the fund and the SGA
        request too. Money coming in is either new revenue or a purchase being
        credited back, never both, and a refund in the queue carries no routing
        of its own: ReconcileForm copies it, fund included, off the entry being
        reversed.

     5. Choosing the kind of income fills in the fund it goes into. SGA pays
        each of its three kinds of money into its own pot, so the source and
        the fund are one answer; which fund is data-credits-fund on the
        source's <option>, set from the Revenue Source admin. Like rule 2 it
        only overwrites a box it filled in itself.

   The server enforces all five either way (ParsedTransaction.clean(),
   BaseAllocationForm._check_fund_and_fr_line and _default_fund_from_source,
   and, for rule 4, the direction rules that drop the revenue fields from a
   refund outright). None of this is validation. */
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
            request: $scope.find('select[name$="funding_request"]').first(),
            cross: $scope.find('[name$="allow_cross_year_fr"]').first(),
            category: $scope.find('[name$="lnl_spend_category"]').first(),
            project: $scope.find('[name$="project_tag"]').first(),
            projection: $scope.find('[name$="is_projection"]').first(),
            reason: $scope.find('.fin-partition-reason').first(),
            refund: $scope.find('select[name$="refund_of"]').first(),
            /* ajax-select renders linked_event as a visible text box plus a
               hidden input; the hidden one carries the name, and its wrapper
               holds both. */
            event: $scope.find('[name$="linked_event"]').first(),
            revenueType: $scope.find('[name$="non_event_revenue_type"]').first()
        };
    }

    /* ---- 1. Show the FR pickers only when the fund needs one ------------- */
    function gate($fund) {
        var f = fields($fund);
        if (!f.line.length && !f.request.length) { return; }

        var required = f.fund.find('option:selected').attr('data-requires-fr') === '1';
        if (f.line.length) {
            container(f.line).toggle(required);
            if (f.cross.length) { container(f.cross).toggle(required); }

            if (!required && f.line.val()) {
                // A stale line would be rejected on save, with the error landing
                // on a field that is no longer on screen.
                f.line.val('').trigger('change');
                if (f.cross.length) { f.cross.prop('checked', false); }
            }
        }
        if (f.request.length) {
            container(f.request).toggle(required);
            if (!required && f.request.val()) { f.request.val(''); }
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

    /* ---- 5. The kind of income decides its fund ---------------------------- */
    function creditFund($source) {
        var f = fields($source);
        if (!f.fund.length) { return; }
        adopt(f.fund, $source.find('option:selected').attr('data-credits-fund') || '');
        // The fund may now draw on requests, which brings rule 1 in.
        gate(f.fund);
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

    /* ---- 4. A credit is a refund or it is revenue, never both -------------- */
    function refundGate($refund) {
        var f = fields($refund);
        var isRefund = !!f.refund.val();

        /* The fund and the SGA request go too, but only in the queue:
           ReconcileForm copies them off the purchase being reversed. The entry
           page keeps them, because there a refund is filed like any expense and
           the fund is asked for. */
        var hide = [f.event, f.revenueType];
        if ($refund.closest('.fin-queue-row').length) { hide.push(f.fund, f.request); }

        $.each(hide, function (_, $field) {
            if (!$field.length) { return; }
            container($field).toggle(!isRefund);
        });

        /* Deliberately not cleared. In the queue the server drops both fields
           from a refund outright -- the event comes off the purchase being
           reversed -- and on the entry page it drops the revenue type and
           saves the event as it stands. Blanking an ajax-select by hand means
           reaching past the visible box into the hidden input that actually
           carries the value, which is a good way to leave the two disagreeing
           if this rule ever moves. Hiding says the same thing and cannot lie
           about what was submitted. */
    }

    function bind(root) {
        $(root).find('select[name$="refund_of"]').each(function () {
            var $refund = $(this);
            if ($refund.data('fin-refund-gate')) { return; }
            $refund.data('fin-refund-gate', true);
            $refund.on('change', function () { refundGate($refund); });
            refundGate($refund);
        });

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

        $(root).find('select[name$="non_event_revenue_type"]').each(function () {
            var $source = $(this);
            if ($source.data('fin-credits')) { return; }
            $source.data('fin-credits', true);
            var f = fields($source);
            // The fund is released from the source the moment it is picked by
            // hand, as the category is released from an FR line.
            if (f.fund.length && !f.fund.data('fin-watched-fund')) {
                f.fund.data('fin-watched-fund', true);
                f.fund.on('change', function (event) {
                    if (event.namespace === 'fin-inherit') { return; }
                    // The attribute too: jQuery re-reads data-* once the cached
                    // value is gone, which would quietly re-lend the box.
                    f.fund.removeData('fin-inherited').removeAttr('data-fin-inherited');
                });
            }
            $source.on('change', function () { creditFund($source); });
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
