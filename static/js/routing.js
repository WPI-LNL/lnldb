/* How the routing fields react to each other on any allocation form.

   Six rules. The first two, the fifth and the sixth are about not making the
   Treasurer type something the database already knows; the third is about
   asking only when it matters; the fourth is about not asking two questions
   where only one can be answered:

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

     6. The funding request narrows its lines. Every line picker has a
        request box beside it -- in the queue filled in from the request number
        in the memo even when the memo does not say which line, on a saved
        entry from the line it holds. The picker lists each request's lines
        indented under it, one <optgroup> a request. Choosing a request leaves
        only that request's group in the picker (each line's <option> carries
        data-request); choosing a line sets the request to the one it is on.
        "Any request" puts every line back.

   The server enforces all six either way (ParsedTransaction.clean(),
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
            /* The request the line is picked from (rule 6) -- not the model's
               funding_request, which is the one SGA pays back or takes back. */
            lineRequest: $scope.find('select[name$="fr_request"]').first(),
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
            if (f.lineRequest.length) {
                container(f.lineRequest).toggle(required);
                if (!required && f.lineRequest.val()) {
                    f.lineRequest.val('');
                    narrowLines(f.lineRequest);
                }
            }

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

    /* ---- 6. The request narrows its lines --------------------------------- */

    /* Groups are taken out rather than hidden: a hidden <option> can still be
       reached from the keyboard, and some browsers show it anyway. The whole
       list is kept on the picker the first time, and every narrowing starts
       again from it.

       A request's <optgroup> is the request of the lines in it; the empty
       "---------" option sits outside every group and always stays. */
    function allLines($line) {
        var $all = $line.data('fin-all-lines');
        if (!$all) {
            $all = $line.children().clone();
            $line.data('fin-all-lines', $all);
        }
        return $all;
    }

    function narrowLines($lineRequest) {
        var f = fields($lineRequest);
        if (!f.line.length) { return; }
        var $all = allLines(f.line);
        var request = String($lineRequest.val() || '');
        var current = String(f.line.val() || '');
        f.line.empty().append($all.filter(function () {
            var $item = $(this);
            if (!request) { return true; }
            if (!$item.is('optgroup')) { return !this.value || $item.attr('data-request') === request; }
            return $item.children('option').first().attr('data-request') === request;
        }).clone());

        var kept = current && f.line.find('option[value="' + current + '"]').length;
        f.line.val(kept ? current : '');
        if (current && !kept) {
            // The line lent the category and project; one that has gone takes
            // them back (rule 2).
            f.line.trigger('change');
        }
    }

    function followLine($line) {
        var f = fields($line);
        if (!f.lineRequest.length || !$line.val()) { return; }
        var owner = $line.find('option:selected').attr('data-request') || '';
        if (owner && String(f.lineRequest.val() || '') !== owner &&
                f.lineRequest.find('option[value="' + owner + '"]').length) {
            f.lineRequest.val(owner);
            narrowLines(f.lineRequest);
        }
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
            $line.on('change', function () {
                inherit($line);
                followLine($line);
            });
        });

        $(root).find('select[name$="fr_request"]').each(function () {
            var $request = $(this);
            if ($request.data('fin-narrow')) { return; }
            $request.data('fin-narrow', true);
            $request.on('change', function () { narrowLines($request); });
            // Filled in from the memo, so the line picker starts narrowed.
            if ($request.val()) { narrowLines($request); }
        });
    }

    /* A row copied from another copies the line picker as it stands on
       screen, which is only one request's lines if that row's picker was
       narrowed (rule 6) -- clone() takes the <option>s showing, not the whole
       list kept aside. So the copy takes the whole list back from the row it
       was copied from before it is wired up. */
    function restoreLines(root, source) {
        var $line = $(root).find('select[name$="fr_line_target"]').first();
        var $from = $(source).find('select[name$="fr_line_target"]').first();
        if (!$line.length || !$from.data('fin-all-lines')) { return; }
        $line.empty().append(allLines($from).clone()).val('');
    }

    $(function () { bind(document); });

    // The split modal and the queue both add rows after load; a row copied
    // from another says which as `source`.
    $(document).on('fin:rows-added', function (event, root, source) {
        if (root && source) { restoreLines(root, source); }
        bind(root || document);
    });
})(jQuery);
