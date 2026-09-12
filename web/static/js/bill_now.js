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

const PAID_HELP = 'Generates the statement, records the full payment today with the note above (income goes to the ledger), and opens the receipt. Use this only when the money has actually arrived.';
const UNPAID_HELP = 'The statement opens on the Statements page: view or email it there, then Record Payment. Once paid, its PDF is the receipt.';

document.addEventListener('DOMContentLoaded', function() {
    const box = document.getElementById('bill-now-paid-now');
    if (!box) return;
    box.addEventListener('change', function() {
        document.getElementById('bill-now-note-row').style.display = box.checked ? '' : 'none';
        document.getElementById('bill-now-help').textContent = box.checked ? PAID_HELP : UNPAID_HELP;
        document.getElementById('bill-now-confirm').textContent = box.checked ? 'Generate & Record Payment' : 'Generate Statement';
        if (box.checked) document.getElementById('bill-now-note').focus();
    });
});

function closeBillNow() {
    document.getElementById('bill-now-modal').style.display = 'none';
}

function confirmBillNow() {
    const btn = document.getElementById('bill-now-btn');
    const confirm = document.getElementById('bill-now-confirm');
    const paidNow = document.getElementById('bill-now-paid-now').checked;
    const note = paidNow ? document.getElementById('bill-now-note').value.trim() : '';
    withButtonDisabled(confirm, () => fetch(`/statements/bill-now/${btn.dataset.entryId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paid_now: paidNow, note: note })
    })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                // The unsaved-changes guard only fires on a dirty form;
                // a locked entry with nothing typed navigates cleanly.
                // A paid statement lives under the Paid filter; ?statement=
                // pins it visible either way.
                const filter = data.payment && data.payment.status === 'paid' ? '&filter=paid' : '';
                window.location.href = `/statements/?statement=${data.statement_id}${filter}`;
            } else {
                alert('Error: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(() => alert('Error generating statement')));
}
