document.addEventListener('DOMContentLoaded', function() {
    // Alert auto-close helper
    const alerts = document.querySelectorAll('.alert-custom');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
});

// Student search filter for fee entry / voucher generation
function initStudentSearch(inputId, listId, selectId) {
    const input = document.getElementById(inputId);
    const select = document.getElementById(selectId);
    
    if (!input || !select) return;
    
    // Create suggestion list dynamically
    const wrapper = input.parentElement;
    const suggestions = document.createElement('div');
    suggestions.id = listId;
    suggestions.className = 'suggestions-list d-none';
    wrapper.appendChild(suggestions);
    
    // Extract student options from the hidden select
    const students = [];
    for (let option of select.options) {
        if (option.value) {
            students.push({
                id: option.value,
                name: option.getAttribute('data-name') || option.text,
                father: option.getAttribute('data-father') || '',
                class: option.getAttribute('data-class') || ''
            });
        }
    }
    
    // Handle input typing
    input.addEventListener('input', function() {
        const query = this.value.trim().toLowerCase();
        
        if (!query) {
            suggestions.classList.add('d-none');
            return;
        }
        
        const filtered = students.filter(s => 
            s.name.toLowerCase().includes(query) || 
            s.father.toLowerCase().includes(query) ||
            s.class.toLowerCase().includes(query) ||
            s.id.includes(query)
        ).slice(0, 10); // Limit to top 10 results
        
        renderSuggestions(filtered);
    });
    
    // Hide suggestions when clicking outside
    document.addEventListener('click', function(e) {
        if (e.target !== input && e.target !== suggestions) {
            suggestions.classList.add('d-none');
        }
    });
    
    // Focus in shows list if input has query
    input.addEventListener('focus', function() {
        if (this.value.trim()) {
            suggestions.classList.remove('d-none');
        }
    });
    
    function renderSuggestions(list) {
        if (list.length === 0) {
            suggestions.innerHTML = '<div class="suggestion-item text-muted">No student found</div>';
            suggestions.classList.remove('d-none');
            return;
        }
        
        suggestions.innerHTML = '';
        list.forEach(student => {
            const div = document.createElement('div');
            div.className = 'suggestion-item';
            div.innerHTML = `
                <div class="fw-bold">${student.name} <span class="badge badge-class float-end">${student.class}</span></div>
                <div class="text-secondary small">Father: ${student.father} | ID: ${student.id}</div>
            `;
            
            div.addEventListener('click', function() {
                input.value = student.name;
                select.value = student.id;
                suggestions.classList.add('d-none');
                
                // Trigger change event on select to auto-load student fee details
                const event = new Event('change');
                select.dispatchEvent(event);
            });
            
            suggestions.appendChild(div);
        });
        
        suggestions.classList.remove('d-none');
    }
}
