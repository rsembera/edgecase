/**
 * Wait List page — remove-from-list confirmation modal.
 */
document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('waitlist-remove-modal');
    const form = document.getElementById('waitlist-remove-form');
    const nameEl = document.getElementById('waitlist-remove-name');
    if (!modal || !form) return;

    function closeModal() {
        modal.classList.remove('active');
    }

    document.querySelectorAll('.waitlist-remove-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            nameEl.textContent = btn.dataset.name;
            form.action = btn.dataset.action;
            modal.classList.add('active');
        });
    });

    document.getElementById('waitlist-remove-cancel').addEventListener('click', closeModal);

    modal.addEventListener('click', function(e) {
        if (e.target === modal) closeModal();
    });

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') closeModal();
    });
});
