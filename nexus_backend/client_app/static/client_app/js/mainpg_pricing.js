
  (function initPricingToggle() {
    const btnMonthly = document.getElementById('bill-m');
    const btnYearly = document.getElementById('bill-y');
    const priceElements = document.querySelectorAll('.plan-price');
    const periodElements = document.querySelectorAll('.plan-period');
    const saveBadges = document.querySelectorAll('.save-badge');

    if (!btnMonthly || !btnYearly) return;

    let currentBilling = 'monthly'; // default

    function updatePricing(billingType) {
      currentBilling = billingType;
      
      // Update button styles
      if (billingType === 'monthly') {
        btnMonthly.classList.add('bg-white', 'shadow');
        btnMonthly.classList.remove('text-gray-600');
        btnMonthly.setAttribute('aria-selected', 'true');
        
        btnYearly.classList.remove('bg-white', 'shadow');
        btnYearly.classList.add('text-gray-600');
        btnYearly.setAttribute('aria-selected', 'false');
      } else {
        btnYearly.classList.add('bg-white', 'shadow');
        btnYearly.classList.remove('text-gray-600');
        btnYearly.setAttribute('aria-selected', 'true');
        
        btnMonthly.classList.remove('bg-white', 'shadow');
        btnMonthly.classList.add('text-gray-600');
        btnMonthly.setAttribute('aria-selected', 'false');
      }

      // Update prices and badges
      priceElements.forEach(el => {
        const monthlyPrice = parseFloat(el.getAttribute('data-monthly'));
        const yearlyPrice = parseFloat(el.getAttribute('data-yearly'));
        
        if (billingType === 'monthly') {
          el.textContent = '$' + monthlyPrice;
        } else {
          // Calculate monthly price from yearly (yearly / 12)
          const monthlyFromYearly = Math.round(yearlyPrice / 12);
          el.textContent = '$' + monthlyFromYearly;
        }
      });

      // Update period text
      periodElements.forEach(el => {
        if (billingType === 'monthly') {
          el.textContent = '/mo';
        } else {
          el.textContent = '/mo';
        }
      });

      // Show/hide save badges
      saveBadges.forEach(badge => {
        if (billingType === 'yearly') {
          badge.classList.remove('hidden');
        } else {
          badge.classList.add('hidden');
        }
      });

      // Announce to screen readers
      const announceText = billingType === 'monthly' 
        ? btnMonthly.getAttribute('data-announce') 
        : btnYearly.getAttribute('data-announce');
      
      if (announceText) {
        // Create temporary announcement element for accessibility
        const announcement = document.createElement('div');
        announcement.setAttribute('role', 'status');
        announcement.setAttribute('aria-live', 'polite');
        announcement.className = 'sr-only';
        announcement.textContent = announceText;
        document.body.appendChild(announcement);
        setTimeout(() => announcement.remove(), 1000);
      }
    }

    // Event listeners
    btnMonthly.addEventListener('click', () => updatePricing('monthly'));
    btnYearly.addEventListener('click', () => updatePricing('yearly'));

    // Initialize with monthly
    updatePricing('monthly');
  })();
