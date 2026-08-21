/* Ingestion queue: the import panel, the per-row "More" fold, allocating one
   row at a time, and applying an auto-suggest with one click. */
(function ($) {
    'use strict';

    /* ---- Import panel -----------------------------------------------------
       Folded away behind a button. Importing happens once a month; the rest of
       the month this page is for reconciling, and the drop zone was the first
       thing between the Treasurer and the work. */
    $('#fin-import-toggle').on('click', function () {
        var $button = $(this);
        var open = $('#fin-import-panel').toggleClass('is-folded').hasClass('is-folded') === false;
        $button.attr('aria-expanded', open ? 'true' : 'false')
               .toggleClass('btn-primary', open).toggleClass('btn-default', !open);
    });

    /* ---- The per-row fold --------------------------------------------------
       Project, the event a sub-rental was bought for, the partition and the
       cross-year opt-in are all real, and all rare: seven of 253 lines on a
       year's export carry a project. Kept one click away rather than on screen
       twenty-five times. */
    function setFold($row, open) {
        $row.find('.fin-fields-more').toggleClass('is-folded', !open);
        $row.find('.fin-more-toggle').attr('aria-expanded', open ? 'true' : 'false');
    }

    $(document).on('click', '.fin-more-toggle', function () {
        var $button = $(this);
        setFold($button.closest('.fin-queue-row'),
                $button.attr('aria-expanded') !== 'true');
    });

    /* ---- Drag and drop ---------------------------------------------------- */
    var $zone = $('#fin-dropzone');
    var $input = $('#fin-upload-form input[type="file"]');
    var $name = $('#fin-file-name');
    var $btn = $('#fin-upload-btn');

    function showFile(files) {
        if (files && files.length) {
            $name.text(files[0].name);
            $btn.prop('disabled', false);
        } else {
            $name.text('');
            $btn.prop('disabled', true);
        }
    }

    if ($zone.length) {
        $zone.on('click', function () { $input.trigger('click'); });
        $('#fin-browse').on('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            $input.trigger('click');
        });

        $input.on('change', function () { showFile(this.files); });

        // Stop the browser from navigating away when a file misses the zone.
        $(document).on('dragover drop', function (e) { e.preventDefault(); });

        $zone.on('dragenter dragover', function (e) {
            e.preventDefault();
            e.stopPropagation();
            $zone.addClass('is-dragover');
        });

        $zone.on('dragleave dragend', function (e) {
            e.preventDefault();
            e.stopPropagation();
            $zone.removeClass('is-dragover');
        });

        $zone.on('drop', function (e) {
            e.preventDefault();
            e.stopPropagation();
            $zone.removeClass('is-dragover');
            var files = e.originalEvent.dataTransfer && e.originalEvent.dataTransfer.files;
            if (files && files.length) {
                // Assigning to .files keeps the plain form POST working -- no
                // XHR needed, so CSRF and the normal redirect flow are unchanged.
                try {
                    $input[0].files = files;
                } catch (err) {
                    var dt = new DataTransfer();
                    dt.items.add(files[0]);
                    $input[0].files = dt.files;
                }
                showFile(files);
            }
        });
    }

    /* ---- Allocate one row without disturbing the others -------------------- */

    /* The queue is worked a screenful at a time: you fill in five rows, then
       start allocating them. Submitting the form used to reload the page,
       which threw away everything typed into every other row. So each row is
       posted on its own and the answer is applied to that row alone.

       Without JavaScript the same forms still submit and redirect as before. */

    function rowMessage($row, text, kind) {
        var $note = $row.find('.fin-queue-note');
        if (!$note.length) {
            $note = $('<div class="fin-queue-note"></div>').appendTo($row.find('.fin-queue-body'));
        }
        $note.attr('class', 'fin-queue-note fin-queue-note-' + kind).text(text);
        return $note;
    }

    /* ---- Undo -------------------------------------------------------------
       The moment you notice you filed a line wrong is the moment right after
       you filed it, so the way back is offered there and then rather than
       three pages away in the ledger. The row is kept in the DOM, greyed out,
       until the window closes -- undoing has to put the Treasurer's own
       answers back in front of them, and the only copy of those answers is
       the form still sitting in that row. */

    var UNDO_MS = 12000;

    function undoButton($row, pk) {
        var $note = $row.find('.fin-queue-note');
        var $undo = $('<button type="button" class="fin-queue-undo">Undo</button>');
        $undo.appendTo($note);

        var timer = window.setTimeout(function () {
            $row.slideUp(200, function () { $row.remove(); });
        }, UNDO_MS);

        $undo.on('click', function () {
            window.clearTimeout(timer);
            $undo.prop('disabled', true).text('Undoing...');
            $.ajax({
                url: undoUrl(pk),
                method: 'POST',
                data: {csrfmiddlewaretoken: csrfToken()},
                headers: {'X-Requested-With': 'XMLHttpRequest'}
            }).done(function (data) {
                if (!data || !data.ok) {
                    rowMessage($row, (data && data.message) || 'That could not be undone.', 'error');
                    return;
                }
                // Back to an ordinary, editable row with everything the
                // Treasurer typed still in it.
                $row.removeClass('fin-queue-done');
                $row.find('.fin-queue-note').remove();
                $row.find('button[type="submit"]').prop('disabled', false).removeClass('fin-busy');
                updateCounts(1);
            }).fail(function (xhr) {
                var data = xhr.responseJSON;
                rowMessage($row, (data && data.message) ||
                           'That could not be undone. Reload the page and try again.', 'error');
            });
        });
    }

    function undoUrl(pk) {
        // Built from the row's own allocate action so the URL prefix this app
        // is mounted under is never guessed at.
        return String($('#txn-' + pk).find('form').attr('action'))
            .replace(/reconcile\/$/, 'undo/');
    }

    function csrfToken() {
        return $('input[name="csrfmiddlewaretoken"]').first().val();
    }

    function clearErrors($form) {
        $form.find('.fin-field-error').remove();
        $form.find('.has-error').removeClass('has-error');
        $form.closest('.fin-queue-row').find('.fin-queue-note').remove();
    }

    function showErrors($form, errors, reference) {
        var unplaced = [];
        $.each(errors, function (field, messages) {
            // Field names are prefixed per row: txn12-fund_source.
            var $field = $form.find('[name$="-' + field + '"], [name="' + field + '"]').first();
            var text = messages.join(' ');
            if ($field.length) {
                var $group = $field.closest('.form-group');
                $group.addClass('has-error');
                $('<div class="fin-field-error"></div>').text(text).appendTo($group);
                // An error pointing at a folded field would otherwise be
                // invisible, which is worse than the clutter the fold removes.
                if ($group.closest('.fin-fields-more').length) {
                    setFold($form.closest('.fin-queue-row'), true);
                }
            } else {
                unplaced.push(text);
            }
        });
        if (unplaced.length) {
            rowMessage($form.closest('.fin-queue-row'), unplaced.join(' '), 'error');
        } else {
            rowMessage($form.closest('.fin-queue-row'),
                       reference + ': check the highlighted fields.', 'error');
        }
    }

    function updateCounts(delta) {
        var $count = $('.fin-stat-value').first();
        var current = parseInt($count.text().replace(/[^0-9-]/g, ''), 10);
        if (!isNaN(current)) {
            var next = Math.max(0, current + delta);
            $count.text(next);
            $count.toggleClass('text-warning', next > 0).toggleClass('text-success', next === 0);
        }
    }

    $(document).on('submit', '.fin-queue-body form', function (event) {
        var $form = $(this);
        var $row = $form.closest('.fin-queue-row');
        var $submit = $form.find('button[type="submit"]');

        event.preventDefault();
        clearErrors($form);
        $submit.prop('disabled', true).addClass('fin-busy');

        $.ajax({
            url: $form.attr('action'),
            method: 'POST',
            data: $form.serialize(),
            headers: {'X-Requested-With': 'XMLHttpRequest'}
        }).done(function (data) {
            if (!data || !data.ok) {
                $submit.prop('disabled', false).removeClass('fin-busy');
                return;
            }
            if (data.done) {
                // Fully allocated, so it has left the queue. Faded rather than
                // yanked, so the eye can follow what happened -- and it stays
                // put while the undo window is open.
                var pk = $row.attr('id').replace('txn-', '');
                $row.addClass('fin-queue-done');
                rowMessage($row, data.message, 'success');
                updateCounts(-1);
                undoButton($row, pk);
                $(document).trigger('fin:row-done', [pk]);
            } else {
                // A partial allocation leaves work behind, so the row stays and
                // says how much is still loose.
                $submit.prop('disabled', false).removeClass('fin-busy');
                rowMessage($row, data.message + ' ' + data.unallocated + ' still unallocated.',
                           'success');
                $form[0].reset();
            }
        }).fail(function (xhr) {
            $submit.prop('disabled', false).removeClass('fin-busy');
            var data = xhr.responseJSON;
            if (data && data.errors) {
                showErrors($form, data.errors, data.reference || 'This line');
            } else {
                rowMessage($row, 'That could not be saved. Reload the page and try again.',
                           'error');
            }
        });
    });


    /* ---- Bulk reconcile ----------------------------------------------------
       The per-row form is right when the rows differ. When they do not -- a
       dozen supply orders on one export, all Consumables out of the standing
       budget -- it asks the same two questions a dozen times. Selecting rows
       and answering once is the ledger's bulk bar, pointed at this page, and
       it behaves the same way down to the shift-click range select. */

    var $qbar = $('#fin-qbulk-bar');

    if ($qbar.length) {
        var $qcount = $('#fin-qbulk-count');
        var $qselected = $('#fin-qbulk-selected');
        var lastChecked = null;

        function checkedIds() {
            return $('.fin-queue-check:checked').map(function () { return this.value; }).get();
        }

        function refreshBulk() {
            var ids = checkedIds();
            $qcount.text(ids.length);
            $qselected.val(ids.join(','));
            $qbar.toggleClass('is-visible', ids.length > 0);
            $('.fin-queue-check').each(function () {
                $(this).closest('.fin-queue-row').toggleClass('fin-queue-selected', this.checked);
            });
        }

        $(document).on('click', '.fin-queue-check', function (e) {
            // Shift-click takes the run between the two, as the ledger does.
            if (e.shiftKey && lastChecked && lastChecked !== this) {
                var boxes = $('.fin-queue-check');
                var start = boxes.index(lastChecked);
                var end = boxes.index(this);
                var state = this.checked;
                boxes.slice(Math.min(start, end), Math.max(start, end) + 1)
                     .prop('checked', state);
            }
            lastChecked = this;
            refreshBulk();
        });

        $('#fin-qbulk-cancel').on('click', function () {
            $('.fin-queue-check').prop('checked', false);
            lastChecked = null;
            refreshBulk();
        });

        $('#fin-qbulk-form').on('submit', function () {
            $qselected.val(checkedIds().join(','));
        });

        // A row allocated on its own leaves the queue, so its selection has to
        // go with it or the bar would keep counting a row that is not there.
        $(document).on('fin:row-done', function (event, pk) {
            $('#txn-' + pk).find('.fin-queue-check').prop('checked', false);
            refreshBulk();
        });

        refreshBulk();
    }

    /* ---- Auto-suggest badges ----------------------------------------------
       Every field that still offers a chip is a <select>: fund, spend category,
       funding request line, project. The event picker used to offer them too
       and needed a branch of its own, because ajax-select keeps its value in a
       hidden input beside the visible text box -- but the memo names the event
       outright, so that field is filled in server-side now and offers nothing
       to click. The branch went with the chips. */
    $(document).on('click', '.fin-suggest', function () {
        var $badge = $(this);
        var targetId = $badge.data('target');
        var value = String($badge.data('value'));
        if (!targetId) { return; }

        var $target = $('#' + targetId);
        if (!$target.length) { return; }

        $target.val(value).trigger('change');
        $badge.addClass('fin-suggest-applied');
    });
})(jQuery);
