
// Fix Leaflet map display in modal: call invalidateSize when showing map step
window.showOrderStep2 = function() {
  // Hide all steps
  document.getElementById('orderStep1').classList.add('hidden');
  document.getElementById('orderStep2').classList.remove('hidden');
  document.getElementById('orderStep3').classList.add('hidden');
  // Invalidate Leaflet map size after a short delay to ensure visibility
  setTimeout(function() {
    if (window.map && typeof window.map.invalidateSize === 'function') {
      window.map.invalidateSize();
    }
  }, 200);
};

// Example: attach to Next button on step 1
document.addEventListener('DOMContentLoaded', function() {
  var nextBtn = document.getElementById('nextStep1');
  if (nextBtn) {
    nextBtn.addEventListener('click', function() {
      window.showOrderStep2();
    });
  }
});
