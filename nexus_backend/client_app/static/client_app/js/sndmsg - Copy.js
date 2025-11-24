

  (function initContactForm() {
    const contactForm = document.getElementById('contactForm');
    const submitBtn = document.getElementById('submitBtn');
    const btnText = document.getElementById('btnText');
    const btnSpinner = document.getElementById('btnSpinner');
    const alertBox = document.getElementById('contact-alert');
    
    if (!contactForm) return;
    
    // Get CSRF token
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
const formData = new FormData(contactForm);
formData.append('csrfmiddlewaretoken', csrfToken);  // ✅ Add this line

    
    // Clear all error messages
    function clearErrors() {
      const errorElements = document.querySelectorAll('[id^="error-"]');
      errorElements.forEach(el => {
        el.textContent = '';
        el.classList.add('hidden');
      });
      
      // Remove error styling from inputs
      const inputs = contactForm.querySelectorAll('input, textarea');
      inputs.forEach(input => {
        input.classList.remove('border-red-400');
      });
    }
    
    // Show error for specific field
    function showFieldError(fieldName, errorMessage) {
      const errorElement = document.getElementById(`error-${fieldName}`);
      const inputElement = document.getElementById(fieldName);
      
      if (errorElement && inputElement) {
        errorElement.textContent = errorMessage;
        errorElement.classList.remove('hidden');
        inputElement.classList.add('border-red-400');
      }
    }
    
    // Show alert message
    function showAlert(message, isSuccess = true) {
      alertBox.textContent = message;
      alertBox.className = `mb-4 p-4 rounded-lg ${
        isSuccess 
          ? 'bg-green-500/20 border border-green-400 text-green-100' 
          : 'bg-red-500/20 border border-red-400 text-red-100'
      }`;
      alertBox.classList.remove('hidden');
      
      // Auto-hide after 5 seconds
      setTimeout(() => {
        alertBox.classList.add('hidden');
      }, 5000);
    }
    
    // Toggle button loading state
    function setLoading(isLoading) {
      submitBtn.disabled = isLoading;
      if (isLoading) {
        btnText.classList.add('hidden');
        btnSpinner.classList.remove('hidden');
      } else {
        btnText.classList.remove('hidden');
        btnSpinner.classList.add('hidden');
      }
    }
    
    // Handle form submission
    contactForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      
      // Clear previous errors
      clearErrors();
      alertBox.classList.add('hidden');
      
      // Set loading state
      setLoading(true);
      
      // Prepare form data
      const formData = new FormData(contactForm);
      
      try {
        const response = await fetch('{% url "submit_contact_form" %}', {
          method: 'POST',
          headers: {
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest',
          },
          body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
          // Success - show success message and reset form
          showAlert(data.message, true);
          contactForm.reset();
          
          // Scroll to alert
          alertBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
        } else {
          // Validation errors
          if (data.errors) {
            // Show field-specific errors
            for (const [field, errors] of Object.entries(data.errors)) {
              if (errors.length > 0) {
                showFieldError(field, errors[0]);
              }
            }
          }
          
          // Show general error message
          showAlert(data.message || '{% trans "Please correct the errors below." %}', false);
        }
      } catch (error) {
        console.error('Error submitting form:', error);
        showAlert('{% trans "An error occurred. Please try again later." %}', false);
      } finally {
        setLoading(false);
      }
    });
    
    // Clear error on input
    const formInputs = contactForm.querySelectorAll('input, textarea');
    formInputs.forEach(input => {
      input.addEventListener('input', () => {
        const errorElement = document.getElementById(`error-${input.name}`);
        if (errorElement) {
          errorElement.classList.add('hidden');
          input.classList.remove('border-red-400');
        }
      });
    });
  })();
