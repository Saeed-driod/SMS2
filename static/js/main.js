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
    
    // Create suggestion list dynamically if not existing
    let wrapper = input.parentElement;
    let suggestions = document.getElementById(listId);
    if (!suggestions) {
        suggestions = document.createElement('div');
        suggestions.id = listId;
        suggestions.className = 'suggestions-list d-none';
        wrapper.appendChild(suggestions);
    }
    
    // Extract student options from the hidden select
    const students = [];
    for (let option of select.options) {
        if (option.value) {
            students.push({
                id: option.value.toString(),
                name: option.getAttribute('data-name') || option.text,
                father: option.getAttribute('data-father') || '',
                class: option.getAttribute('data-class') || '',
                ac: option.getAttribute('data-ac') || '0',
                unpaid_ac: option.getAttribute('data-unpaid-ac') || '0',
                barcode: 'STD-' + option.value.toString()
            });
        }
    }
    
    function selectStudent(student) {
        input.value = student.name;
        select.value = student.id;
        suggestions.classList.add('d-none');
        
        // Trigger change event on select to auto-load student fee details
        const event = new Event('change');
        select.dispatchEvent(event);
    }
    
    function cleanDigitsMatch(q, id) {
        const clean = q.toLowerCase().replace(/^[a-z]+[-_]?/i, '');
        return clean.length >= 1 && clean === id;
    }
    
    function getFilteredStudents(rawQuery) {
        if (!rawQuery) return [];
        const query = rawQuery.trim().toLowerCase();
        const cleanDigits = query.replace(/^[a-z]+[-_]?/i, '');
        
        return students.filter(s => 
            s.name.toLowerCase().includes(query) || 
            s.father.toLowerCase().includes(query) ||
            s.class.toLowerCase().includes(query) ||
            s.id === query ||
            s.id === cleanDigits ||
            s.barcode.toLowerCase() === query ||
            s.barcode.toLowerCase().includes(query) ||
            s.id.includes(query)
        );
    }
    
    // Handle input typing & barcode scanning
    input.addEventListener('input', function() {
        const query = this.value.trim();
        
        if (!query) {
            suggestions.classList.add('d-none');
            return;
        }
        
        const filtered = getFilteredStudents(query);
        
        // If an exact barcode or ID match was scanned/typed (e.g. from a barcode gun)
        const exactMatch = students.find(s => 
            s.barcode.toLowerCase() === query.toLowerCase() || 
            s.id === query || 
            cleanDigitsMatch(query, s.id)
        );
        
        renderSuggestions(filtered.slice(0, 10));
    });
    
    // Handle barcode scanner Enter key event (scanners emit Enter on scan)
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            const query = this.value.trim();
            if (!query) return;
            
            const filtered = getFilteredStudents(query);
            if (filtered.length > 0) {
                // Prioritize exact barcode / ID match or pick first result
                const exact = filtered.find(s => 
                    s.id === query || 
                    s.barcode.toLowerCase() === query.toLowerCase() || 
                    cleanDigitsMatch(query, s.id)
                ) || filtered[0];
                
                selectStudent(exact);
            }
        }
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
            const filtered = getFilteredStudents(this.value);
            renderSuggestions(filtered.slice(0, 10));
        }
    });
    
    function renderSuggestions(list) {
        if (list.length === 0) {
            suggestions.innerHTML = '<div class="suggestion-item text-muted">No student found for this ID / Barcode</div>';
            suggestions.classList.remove('d-none');
            return;
        }
        
        suggestions.innerHTML = '';
        list.forEach(student => {
            const div = document.createElement('div');
            div.className = 'suggestion-item';
            
            let ac_badge = '';
            const ac_val = parseFloat(student.ac) || 0;
            const unpaid_ac_val = parseFloat(student.unpaid_ac) || 0;
            if (ac_val > 0) {
                if (unpaid_ac_val <= 0) {
                    ac_badge = ' &bull; <span class="badge bg-success bg-opacity-20 text-success border border-success border-opacity-30 py-0.5 px-1.5 small" style="font-size: 0.65rem;">AC Paid</span>';
                } else {
                    ac_badge = ' &bull; <span class="badge bg-warning bg-opacity-20 text-warning border border-warning border-opacity-30 py-0.5 px-1.5 small" style="font-size: 0.65rem;">AC Unpaid: Rs. ' + Math.round(unpaid_ac_val).toLocaleString() + '</span>';
                }
            }
            
            div.innerHTML = `
                <div class="fw-bold">${student.name} <span class="badge badge-class float-end">${student.class}</span></div>
                <div class="text-secondary small">Father: ${student.father} &bull; <span class="badge bg-dark border border-secondary text-info font-monospace" style="font-size: 0.7rem;"><i class="fa-solid fa-barcode me-1"></i>STD-${student.id}</span>${ac_badge}</div>
            `;
            
            div.addEventListener('click', function() {
                selectStudent(student);
            });
            
            suggestions.appendChild(div);
        });
        
        suggestions.classList.remove('d-none');
    }
}
