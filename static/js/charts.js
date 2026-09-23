/* Dashboard charts. Chart.js 2.4 is already loaded globally by base.html.
   All data arrives via a json_script block so nothing is escaped by hand. */
(function () {
    'use strict';

    if (typeof Chart === 'undefined') { return; }

    var payload = document.getElementById('fin-chart-data');
    if (!payload) { return; }

    var data;
    try {
        data = JSON.parse(payload.textContent);
    } catch (e) {
        return;
    }

    function money(value) {
        return '$' + Number(value).toLocaleString(undefined, {
            minimumFractionDigits: 2, maximumFractionDigits: 2
        });
    }

    function compact(value) {
        var n = Number(value);
        if (Math.abs(n) >= 1000) { return '$' + Math.round(n / 1000) + 'k'; }
        return '$' + Math.round(n);
    }

    /* ---- Tooltips that are not trapped in the canvas -----------------------

       Chart.js 2.x paints its tooltip onto the canvas, so it can never be
       wider than the canvas it belongs to. The doughnuts here are 150px wide
       and their labels are things like "Supplies - Personal Protection
       Equipment (PPE): $1,234.56 (12.3%)", so the text simply ran off the edge
       and was clipped.

       Rendering it as one absolutely-positioned element on <body> instead
       costs nothing and removes the constraint entirely: it is laid out by the
       browser, sized by its own content, and clamped to the viewport so it
       cannot run off any edge either. */

    var tipEl = null;

    function tipNode() {
        if (!tipEl) {
            tipEl = document.createElement('div');
            tipEl.className = 'fin-chart-tip';
            document.body.appendChild(tipEl);
        }
        return tipEl;
    }

    function lineFor(model, index) {
        var body = model.body[index];
        var lines = (body && body.lines) || [];
        var colour = (model.labelColors && model.labelColors[index]
                      && model.labelColors[index].backgroundColor) || 'transparent';
        var row = document.createElement('div');
        row.className = 'fin-chart-tip-row';
        var swatch = document.createElement('span');
        swatch.className = 'fin-chart-tip-swatch';
        swatch.style.background = colour;
        row.appendChild(swatch);
        var text = document.createElement('span');
        // textContent, never innerHTML: these strings carry supplier names and
        // spend categories that people typed.
        text.textContent = lines.join(' ');
        row.appendChild(text);
        return row;
    }

    function customTooltip(model) {
        var node = tipNode();

        if (!model || model.opacity === 0 || !model.body) {
            node.style.opacity = '0';
            return;
        }

        node.innerHTML = '';
        (model.title || []).forEach(function (line) {
            var el = document.createElement('div');
            el.className = 'fin-chart-tip-title';
            el.textContent = line;
            node.appendChild(el);
        });
        model.body.forEach(function (_, index) { node.appendChild(lineFor(model, index)); });
        (model.footer || []).forEach(function (line) {
            var el = document.createElement('div');
            el.className = 'fin-chart-tip-footer';
            el.textContent = line;
            node.appendChild(el);
        });

        // Measured after the content is in, because the whole point is that the
        // browser decides how wide this needs to be.
        node.style.opacity = '1';
        var box = this._chart.canvas.getBoundingClientRect();
        var width = node.offsetWidth;
        var height = node.offsetHeight;
        var margin = 8;

        var left = box.left + window.pageXOffset + model.caretX - width / 2;
        var top = box.top + window.pageYOffset + model.caretY - height - 10;

        // Clamped to the viewport rather than to the chart: an edge slice's
        // tooltip belongs beside the slice, and the only hard constraint is
        // that it stays on screen.
        var maxLeft = window.pageXOffset + document.documentElement.clientWidth - width - margin;
        left = Math.max(window.pageXOffset + margin, Math.min(left, maxLeft));
        if (top < window.pageYOffset + margin) {
            // No room above: flip below the caret.
            top = box.top + window.pageYOffset + model.caretY + 14;
        }

        node.style.left = Math.round(left) + 'px';
        node.style.top = Math.round(top) + 'px';
    }

    /* ---- Doughnuts --------------------------------------------------------- */
    function doughnut(canvasId, spec) {
        var el = document.getElementById(canvasId);
        if (!el || !spec || !spec.data || !spec.data.length) { return; }

        var total = spec.data.reduce(function (a, b) { return a + b; }, 0);

        new Chart(el.getContext('2d'), {
            type: 'doughnut',
            data: {
                labels: spec.labels,
                datasets: [{
                    data: spec.data,
                    backgroundColor: spec.colors,
                    borderWidth: 1,
                    borderColor: '#fff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                cutoutPercentage: 58,
                // The legend beside the canvas already names every slice.
                legend: { display: false },
                tooltips: {
                    enabled: false,
                    custom: customTooltip,
                    callbacks: {
                        label: function (item, d) {
                            var value = d.datasets[0].data[item.index];
                            var pct = total ? (value / total * 100).toFixed(1) : '0.0';
                            return d.labels[item.index] + ': ' + money(value) + ' (' + pct + '%)';
                        }
                    }
                }
            }
        });
    }

    doughnut('fin-chart-categories', data.categories);
    doughnut('fin-chart-clienttypes', data.client_types);
    doughnut('fin-chart-services', data.services);

    /* ---- Cash flow --------------------------------------------------------- */
    var cashEl = document.getElementById('fin-cashflow');
    if (cashEl && data.cash_flow && data.cash_flow.labels.length) {
        new Chart(cashEl.getContext('2d'), {
            type: 'bar',
            data: {
                labels: data.cash_flow.labels,
                datasets: [
                    {
                        label: 'Money in',
                        data: data.cash_flow.revenue,
                        backgroundColor: '#59A14F',
                        borderWidth: 0
                    },
                    {
                        label: 'Money out',
                        data: data.cash_flow.expense,
                        backgroundColor: '#E15759',
                        borderWidth: 0
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                legend: {
                    display: true,
                    position: 'top',
                    labels: { boxWidth: 12, fontSize: 11, usePointStyle: false }
                },
                scales: {
                    xAxes: [{
                        gridLines: { display: false },
                        ticks: { fontSize: 11 }
                    }],
                    yAxes: [{
                        ticks: {
                            beginAtZero: true,
                            fontSize: 11,
                            callback: function (value) { return compact(value); }
                        },
                        gridLines: { color: '#eceff1' }
                    }]
                },
                tooltips: {
                    enabled: false,
                    custom: customTooltip,
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        label: function (item, d) {
                            return d.datasets[item.datasetIndex].label + ': ' + money(item.yLabel);
                        },
                        footer: function (items) {
                            if (items.length < 2) { return ''; }
                            var net = Number(items[0].yLabel) - Number(items[1].yLabel);
                            return 'Net: ' + money(net);
                        }
                    }
                }
            }
        });
    }
})();
