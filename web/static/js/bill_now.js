/**
 * Bill Now — on-demand statement from an entry form.
 *
 * Preview what would be billed (same predicate the generator uses), let the
 * user confirm, generate through the month-end code path, then hand off to
 * the Statements page with the new statement pinned and highlighted.
 * Nothing here touches payment: Record Payment lives on that page.
 */
function openBillNow() {
    const btn = document.getElementById('bill-now-btn');
    const modal = document.getElementById('bill-now-modal');
    const scope = document.getElementById('bill-now-scope');
    const confirm = document.getElementById('bill-now-confirm');
    scope.innerHTML = '<p class="text-muted">Checking…</p>';
    confirm.disabled = true;
    modal.style.display = 'flex';

    fetch(`/statements/bill-now/preview/${btn.dataset.entryId}`)
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                scope.innerHTML = `<p class="text-muted">${escapeHtml(data.error || 'Cannot bill this entry')}</p>`;
                return;
            }
            const rows = data.entries.map(e =>
                `<tr><td>${escapeHtml(e.date)}</td><td>${escapeHtml(e.description)}</td><td class="bill-now-amount">$${e.amount.toFixed(2)}</td></tr>`
            ).join('');
            scope.innerHTML = `
                <p class="text-muted">${escapeHtml(data.period)}</p>
                <table class="bill-now-table">${rows}
                    <tr class="bill-now-total"><td></td><td>Total</td><td class="bill-now-amount">$${data.total.toFixed(2)}</td></tr>
                </table>`;
            document.getElementById('bill-now-intro').textContent = data.entries.length === 1
                ? 'Generate a statement for this entry.'
                : `Generate a statement for these ${data.entries.length} unbilled entries — everything this client owes as of this one.`;
            confirm.disabled = false;
        })
        .catch(() => { scope.innerHTML = '<p class="text-muted">Could not load preview.</p>'; });
}

function closeBillNow() {
    document.getElementById('bill-now-modal').style.display = 'none';
}

function confirmBillNow() {
    const btn = document.getElementById('bill-now-btn');
    const confirm = document.getElementById('bill-now-confirm');
    withButtonDisabled(confirm, () => fetch(`/statements/bill-now/${btn.dataset.entryId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                // The unsaved-changes guard only fires on a dirty form;
                // a locked entry with nothing typed navigates cleanly.
                window.location.href = `/statements/?statement=${data.statement_id}`;
            } else {
                alert('Error: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(() => alert('Error generating statement')));
}
