/**
 * D3.js Audit Reason Breakdown Bar Chart
 */
(function() {
    'use strict';
    
    d3.json('/data/audit-data.json').then(function(data) {
        if (!data || !Object.keys(data.categories).length) return;
        
        const container = document.getElementById('audit-chart');
        if (!container) return;
        
        const width = Math.max(container.clientWidth, 500);
        const height = 400;
        const margin = {top: 20, right: 30, bottom: 80, left: 140};
        
        d3.select('#audit-chart').selectAll('*').remove();
        
        const svg = d3.select('#audit-chart')
            .append('svg')
            .attr('width', width)
            .attr('height', height + margin.top + margin.bottom);
        
        const g = svg.append('g')
            .attr('transform', `translate(${margin.left},${margin.top})`);
        
        const categories = Object.entries(data.categories)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 15);
        
        const xScale = d3.scaleLinear()
            .domain([0, d3.max(categories, d => d[1])])
            .range([0, width - margin.left - margin.right]);
        
        const yScale = d3.scaleBand()
            .domain(categories.map(d => d[0]))
            .range([0, height])
            .padding(0.2);
        
        // Color palette
        const colorPalette = ['#2469ae','#34a853','#fbbc04','#ea4335','#4285f4',
            '#9b72cf','#ff6d01','#46b8c6','#7bd4a2','#ffc90e',
            '#c5221f','#311b92','#00695c','#ad1457','#616161'];
        
        // Bars
        g.selectAll('.bar')
            .data(categories)
            .enter()
            .append('rect')
            .attr('class', 'bar')
            .attr('x', 0)
            .attr('y', d => yScale(d[0]))
            .attr('width', d => xScale(d[1]))
            .attr('height', yScale.bandwidth())
            .attr('fill', (d, i) => colorPalette[i % colorPalette.length])
            .style('cursor', 'pointer')
            .on('mouseover', function(event, d) {
                d3.select(this).attr('opacity', 0.8);
            })
            .on('mouseout', function() {
                d3.select(this).attr('opacity', 1);
            });
        
        // X axis
        g.append('g')
            .attr('class', 'axis')
            .attr('transform', `translate(0,${height})`)
            .call(d3.axisBottom(xScale).ticks(5));
        
        // Y axis
        g.append('g')
            .attr('class', 'axis')
            .call(d3.axisLeft(yScale))
            .selectAll('text')
            .attr('font-size', '11px');
        
        // Total label
        g.append('text')
            .attr('x', xScale(d3.max(categories, d => d[1])))
            .attr('y', -5)
            .attr('text-anchor', 'end')
            .style('font-size', '12px')
            .style('fill', '#6c757d')
            .text(`Total: ${data.total_audit_entries.toLocaleString()} entries`);
            
    }).catch(err => console.error('Audit chart load failed:', err));
})();
