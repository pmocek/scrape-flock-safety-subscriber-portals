/**
 * D3.js Force-Directed Network Graph for Data Sharing Flows
 */
(function() {
    'use strict';

    d3.json('/data/network-graph.json').then(function(data) {
        if (!data || !data.nodes.length) return;

        const container = document.getElementById('network-graph');
        if (!container) return;

        const width = Math.max(container.clientWidth, 600);
        const height = 500;

        const svg = d3.select('#network-graph')
            .append('svg')
            .attr('width', width)
            .attr('height', height)
            .style('border-radius', '4px')
            .style('background', '#fff');

        // Color by status
        const colorMap = {
            active: '#2469ae',
            inactive: '#fbbc04',
            not_found: '#ea4335',
        };

        const simulation = d3.forceSimulation(data.nodes)
            .force('link', d3.forceLink(data.links).id(d => d.id).distance(40))
            .force('charge', d3.forceManyBody().strength(-30))
            .force('center', d3.forceCenter(width / 2, height / 2))
            .force('collision', d3.forceCollide().radius(4));

        // Links
        const link = svg.append('g')
            .selectAll('line')
            .data(data.links)
            .enter()
            .append('line')
            .attr('stroke', '#dee2e6')
            .attr('stroke-width', 0.5);

        // Nodes
        const node = svg.append('g')
            .selectAll('circle')
            .data(data.nodes)
            .enter()
            .append('circle')
            .attr('r', d => Math.min(4, Math.sqrt(d.cameras) || 3))
            .attr('fill', d => colorMap[d.status] || '#6c757d')
            .attr('stroke', '#fff')
            .attr('stroke-width', 1)
            .call(d3.drag()
                .on('start', dragstarted)
                .on('drag', dragged)
                .on('end', dragended));

        // Labels (only for high-camera agencies)
        svg.append('g')
            .selectAll('text')
            .data(data.nodes.filter(d => d.cameras >= 5))
            .enter()
            .append('text')
            .text(d => d.name.split(' ')[0])
            .attr('font-size', '9px')
            .attr('fill', '#495057')
            .attr('dx', 6)
            .attr('dy', 4);

        // Zoom/pan
        const zoom = d3.zoom()
            .scaleExtent([0.1, 4])
            .on('zoom', (event) => {
                svg.attr('transform', event.transform);
            });
        svg.call(zoom);

        simulation.on('tick', () => {
            link
                .attr('x1', d => d.source.x)
                .attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x)
                .attr('y2', d => d.target.y);
            node
                .attr('cx', d => d.x)
                .attr('cy', d => d.y);
            svg.selectAll('text')
                .attr('x', d => d.x)
                .attr('y', d => d.y);
        });

        function dragstarted(event, d) {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x; d.fy = d.y;
        }
        function dragged(event, d) {
            d.fx = event.x; d.fy = event.y;
        }
        function dragended(event, d) {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null; d.fy = null;
        }

    }).catch(err => console.error('Network graph load failed:', err));
})();
