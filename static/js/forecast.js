/* The forecast chart. Chart.js 2.4 is already loaded globally by base.html.
   Every figure arrives through a json_script block, so nothing is escaped by
   hand, and nothing is worked out here: the page's table says the same. */
(function () {
    'use strict';

    if (typeof Chart === 'undefined') { return; }
    var payload = document.getElementById('fin-forecast-data');
    var canvas = document.getElementById('fin-forecast-chart');
    if (!payload || !canvas) { return; }

    var data;
    try {
        data = JSON.parse(payload.textContent);
    } catch (e) {
        return;
    }

    function money(value) {
        return '$' + Number(value).toLocaleString(undefined, {
            minimumFractionDigits: 0, maximumFractionDigits: 0
        });
    }

    function line(label, values, colour, extra) {
        var set = {
            label: label,
            data: values,
            borderColor: colour,
            backgroundColor: colour,
            fill: false,
            pointRadius: 2,
            borderWidth: 2,
            spanGaps: false,
            lineTension: 0
        };
        for (var key in extra || {}) {
            if (Object.prototype.hasOwnProperty.call(extra, key)) { set[key] = extra[key]; }
        }
        return set;
    }

    var reserve = data.labels.map(function () { return data.reserve; });
    var sets = [
        line('Workday cash', data.actual, '#7B8794'),
        line('All of the account, ahead', data.cash, '#9AA5B1', {borderDash: [6, 4], pointRadius: 0}),
        line("LNL's own money, ahead", data.own, '#4E79A7', {borderWidth: 3})
    ];
    if (data.low.length) {
        sets.push(line('Weakest year', data.low, '#4E79A7', {borderDash: [2, 3], borderWidth: 1, pointRadius: 0}));
        sets.push(line('Strongest year', data.high, '#4E79A7', {borderDash: [2, 3], borderWidth: 1, pointRadius: 0}));
    }
    sets.push(line('Minimum reserve', reserve, '#E15759', {borderDash: [8, 4], borderWidth: 1, pointRadius: 0}));

    new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {labels: data.labels, datasets: sets},
        options: {
            responsive: true,
            legend: {position: 'bottom', labels: {boxWidth: 12}},
            tooltips: {
                mode: 'nearest',
                intersect: false,
                callbacks: {
                    label: function (item, chart) {
                        var set = chart.datasets[item.datasetIndex];
                        return set.label + ': ' + money(item.yLabel);
                    }
                }
            },
            scales: {
                yAxes: [{ticks: {callback: function (value) { return money(value); }}}]
            }
        }
    });
}());
