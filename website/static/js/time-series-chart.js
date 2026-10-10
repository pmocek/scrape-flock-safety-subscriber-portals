/**
 * D3.js Time-Series Chart for Agency Detail Pages
 * Renders portal_activity, vehicles_detected, search_volume over time
 */
(function() {
    'use strict';

    // Load series data from Hugo-generated JSON
    const SERIES_DATA = typeof window.AGENCY_SERIES !== 'undefined' ? window.AGENCY_SERIES : null;
    
    if (!SERIES_DATA) return;

    function renderChart(containerId, data, metricKey, label, color) {
        const container = document.getElementById(containerId);
        if (!container || !data || !data.entries.length) return;

        const margin = { top: 20, right: 20, bottom: 40, left: 50 };
        const width = container.clientWidth - margin.left - margin.right;
        const height = 200 - margin.top - margin.bottom;

        d3.select('#' + containerId).selectAll('*').remove();

        const svg = d3.select('#' + containerId)
            .append('svg')
            .attr('width', width + margin.left + margin.right)
            .attr('height', height + margin.top + margin.bottom)
            .append('g')
            .attr('transform', `translate(${margin.left},${margin.top})`);

        // Parse timestamps
        const parseDate = d3.timeParse('%Y-%m-%dT%H:%M:%S');
        const xScale = d3.scaleTime()
            .domain(d3.extent(data.entries, d => parseDate(d.ts)))
            .range([0, width]);

        const yValues = data.entries.map(e => e[metricKey]).filter(v => v != null && v > 0);
        const maxVal = d3.max(yValues) || 100;
        const yScale = d3.scaleLinear()
            .domain([0, maxVal])
            .nice()
            .range([height, 0]);

        // Grid lines
        svg.append('g')
            .attr('class', 'axis')
            .attr('transform', `translate(0,${height})`)
            .call(d3.axisBottom(xScale).ticks(8).tickFormat(d3.timeFormat('%b %Y')));

        svg.append('g')
            .attr('class', 'axis')
            .call(d3.axisLeft(yScale).ticks(5));

        // Line
        const line = d3.line()
            .x(d => xScale(parseDate(d.ts)))
            .y(d => yScale(d[metricKey]))
            .defined(d => d[metricKey] != null);

        svg.append('path')
            .datum(data.entries.filter(e => e[metricKey] != null))
            .attr('fill', 'none')
            .attr('stroke', color)
            .attr('stroke-width', 1.5)
            .attr('d', line);

        // Tooltip
        svg.selectAll('.tooltip-dot')
            .data(data.entries.filter(e => e[metricKey] != null))
            .enter()
            .append('circle')
            .attr('class', 'tooltip-dot')
            .attr('cx', d => xScale(parseDate(d.ts)))
            .attr('cy', d => yScale(d[metricKey]))
            .attr('r', 3)
            .attr('fill', color)
            .style('opacity', 0.6)
            .on('mouseover', function(event, d) {
                d3.select(this).attr('r', 5).style('opacity', 1);
            })
            .on('mouseout', function() {
                d3.select(this).attr('r', 3).style('opacity', 0.6);
            });

        // Axis labels
        svg.append('text')
            .attr('x', width / 2)
            .attr('y', height + 35)
            .attr('text-anchor', 'middle')
            .style('font-size', '11px')
            .style('fill', '#6c757d')
            .text('Date');

        svg.append('text')
            .attr('transform', 'rotate(-90)')
            .attr('x', -height / 2)
            .attr('y', -38)
            .attr('text-anchor', 'middle')
            .style('font-size', '11px')
            .style('fill', '#6c757d')
            .text(label);
    }

    // Render all chart containers on this page
    renderChart('portal-activity-chart', SERIES_DATA, 'status', 'Portal Status Entries', '#2469ae');
    renderChart('vehicles-chart', SERIES_DATA, 'vehicles', 'Vehicles Detected (30-day rolling)', '#34a853');
    renderChart('search-volume-chart', SERIES_DATA, 'searches', 'Searches (30-day rolling)', '#fbbc04');

})();
