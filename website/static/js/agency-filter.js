document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('agency-search');
    const tableBody = document.getElementById('agency-tbody');
    if (!searchInput || !tableBody) return;

    searchInput.addEventListener('input', function() {
        const query = this.value.toLowerCase();
        const rows = tableBody.querySelectorAll('tr[data-name]');
        rows.forEach(row => {
            const name = row.getAttribute('data-name').toLowerCase();
            row.style.display = name.includes(query) ? '' : 'none';
        });
    });
});
