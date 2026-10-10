#!/usr/bin/env node
/**
 * Export data sharing network for D3.js force-directed graph visualization.
 * Reads agency stats.jsonl files to extract shares_data_with relationships.
 */
const fs = require('fs');
const path = require('path');
const os = require('os');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT_FILE = path.join(__dirname, '..', 'website', 'data', 'network-graph.json');

const nodes = new Map(); // slug -> {id, name, cameras, status}
const links = [];        // {source, target}

// Process each agency directory
for (const entry of fs.readdirSync(DATA_DIR)) {
    const statsPath = path.join(DATA_DIR, entry, 'stats.jsonl');
    if (!fs.existsSync(statsPath)) continue;
    
    const latest = readLatestEntry(statsPath);
    if (!latest || latest.portal_status === 'not_found') continue;
    
    const slug = entry;
    const name = latest.page_name || slug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    const status = latest.portal_status || 'active';
    const cameras = latest.total_cameras || 0;
    
    nodes.set(slug, { id: slug, name, cameras, status });
    
    // Extract sharing relationships
    const sharedWith = latest.shares_data_with || [];
    for (const partnerName of sharedWith) {
        // Try to match partner name to a slug via eyesonflock mapping
        const partnerSlug = nameToSlug(partnerName, entriesList());
        if (partnerSlug && partnerSlug !== slug) {
            links.push({ source: slug, target: partnerSlug });
        }
    }
}

// Write output
const output = {
    nodes: Array.from(nodes.values()),
    links: links,
};

fs.mkdirSync(path.dirname(OUTPUT_FILE), { recursive: true });
fs.writeFileSync(OUTPUT_FILE, JSON.stringify(output, null, 2));
console.log(`Exported ${nodes.size} nodes, ${links.length} edges → network-graph.json`);

function readLatestEntry(statsPath) {
    let latest = null;
    for (const line of fs.readFileSync(statsPath, 'utf-8').split('\n')) {
        try {
            const obj = JSON.parse(line.trim());
            if (obj.page_name || obj.portal_status) latest = obj;
        } catch {}
    }
    return latest;
}

function entriesList() {
    const entries = [];
    for (const entry of fs.readdirSync(DATA_DIR)) {
        entries.push(entry);
    }
    return entries;
}

function nameToSlug(name, slugs) {
    // Normalize: lowercase, replace spaces/dashes
    const normalized = normalize(name);
    for (const slug of slugs) {
        if (normalize(slug) === normalized) return slug;
    }
    // Partial match: first word of name
    const firstWord = name.split(' ')[0].toLowerCase();
    for (const slug of slugs) {
        if (slug.includes(firstWord)) return slug;
    }
    return null;
}

function normalize(str) {
    return str.toLowerCase().replace(/[^a-z0-9]/g, '');
}
