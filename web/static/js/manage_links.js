function deleteGroup(groupId, groupName) {
    const modal = document.getElementById('deleteModal');
    const message = document.getElementById('deleteMessage');
    const confirmBtn = document.getElementById('confirmDelete');
    
    message.textContent = `Are you sure you want to delete "${groupName}"?`;
    modal.classList.add('active');
    
    confirmBtn.onclick = async function() {
        try {
            const response = await fetch(`/links/${groupId}/delete`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            if (response.ok) {
                window.location.reload();
            } else {
                alert('Error deleting link group');
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Error deleting link group');
        }
    };
}

function closeDeleteModal() {
    document.getElementById('deleteModal').classList.remove('active');
}

// Close modal on outside click
document.addEventListener('click', function(e) {
    const modal = document.getElementById('deleteModal');
    if (e.target === modal) {
        closeDeleteModal();
    }
});