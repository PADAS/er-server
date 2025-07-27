// Wait for the DOM to be fully loaded
window.addEventListener('DOMContentLoaded', function() {
    var link = document.querySelector('a.viewlink[href="/admin/activity/formbuilderproxy/"]');
    if (link && link.textContent.trim() === 'View') {
        link.textContent = 'View and Edit';
        link.target = '_blank';
    }
});
