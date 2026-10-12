/**
 * Health check trend chart.
 *
 * Stacked area chart of daily check outcomes (ok / error / blocked) from
 * data/health.json, produced by scripts/export-health-data.py.
 */
(function() {
    'use strict';

    const container = document.getElementById('health-chart');
    if (!container || typeof d3 === 'undefined') return;

    const url = container.getAttribute('data-url');
    if (!url) return;

    fetch(url)
        .then(r => r.json())
        .then(render)
        .catch(err => {
            container.innerHTML =
                '<p style="color:var(--color-muted)">Health chart unavailable: ' + err + '</p>';
        });

    function render(data) {
        const daily = data.daily || [];
        if (!daily.length) {
            container.innerHTML =
                '<p style="color:var(--color-muted)">No health check records yet.</p>';
            return;
        }

        const margin = { top: 20, right: 20, bottom: 40, left: 50 };
        const width = Math.max(container.clientWidth || 600, 300) - margin.left - margin.right;
        const height = 240 - margin.top - margin.bottom;

        const parseDay = d3.timeParse('%Y-%m-%d');
        const series = daily.map(d => ({
            date: parseDay(d.date),
            ok: d.ok,
            error: d.error,
            blocked: d.blocked
        })).filter(d => d.date);

        const keys = [
            { key: 'ok', label: 'Reachable', color: '#34a853' },
            { key: 'error', label: 'Error', color: '#ea4335' },
            { key: 'blocked', label: 'Blocked', color: '#fbbc04' }
        ];

        const x = d3.scaleTime()
            .domain(d3.extent(series, d => d.date))
            .range([0, width]);

        const y = d3.scaleLinear()
            .domain([0, d3.max(series, d => d.ok + d.error + d.blocked) || 1])
            .nice()
            .range([height, 0]);

        const svg = d3.select('#health-chart')
            .append('svg')
            .attr('width', width + margin.left + margin.right)
            .attr('height', height + margin.top + margin.bottom)
            .style('max-width', '100%');

        const g = svg.append('g')
            .attr('transform', 'translate(' + margin.left + ',' + margin.top + ')');

        // Axes
        g.append('g')
            .attr('transform', 'translate(0,' + height + ')')
            .call(d3.axisBottom(x).ticks(Math.min(series.length, 6)))
            .selectAll('text')
            .attr('transform', 'rotate(-35)')
            .style('text-anchor', 'end');

        g.append('g').call(d3.axisLeft(y).ticks(5));

        // Stacked areas
        const stacked = d3.stack()
            .keys(keys.map(k => k.key))
            .value((d, i) => d[keys[i].key]);

        g.selectAll('path.area')
            .data(stacked(series))
            .enter()
            .append('path')
            .attr('class', 'area')
            .attr('fill', (d, i) => keys[i].color)
            .attr('fill-opacity', 0.75)
            .attr('d', d3.area()
                .x(d => x(d.data.date))
                .y0(d => y(d[0]))
                .y1(d => y(d[1])));

        // Legend
        const legend = g.append('g')
            .attr('transform', 'translate(0,-10)');

        keys.forEach((k, i) => {
            const item = legend.append('g')
                .attr('transform', 'translate(' + (i * 110) + ',0)');
            item.append('rect')
                .attr('width', 12).attr('height', 12)
                .attr('fill', k.color);
            item.append('text')
                .attr('x', 16).attr('y', 10)
                .style('font-size', '11px')
                .style('fill', 'var(--color-muted)')
                .text(k.label);
        });
    }
})();
