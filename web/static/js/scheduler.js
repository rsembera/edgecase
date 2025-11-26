// Cancel appointment
function cancelAppointment(appointmentId, clientName) {
    if (!confirm(`Cancel appointment with ${clientName}?`)) {
        return;
    }
    
    fetch(`/scheduler/delete/${appointmentId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Reload page to refresh list
            window.location.reload();
        } else {
            alert('Error canceling appointment: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error canceling appointment');
    });
}

// Initialize Lucide icons
document.addEventListener('DOMContentLoaded', function() {
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
});