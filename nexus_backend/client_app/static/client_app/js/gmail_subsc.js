
document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("newsletter-form");

  form.addEventListener("submit", function (e) {
    e.preventDefault();

    const formData = new FormData(form);
    const scriptURL = "https://script.google.com/macros/s/AKfycbyxLnmtlyAnXHBhl0N-rrufQmQlgdyhXY_hkrHJVIIv0qLq_S6JCGY0RV3S3U4bx7sE/exec"; 

    fetch(scriptURL, {
      method: "POST",
      body: formData
    })
    .then(response => response.text())
    .then(text => {
      alert("Thank You for Subscribing"); 
      form.reset();
    })
    .catch(error => {
      console.error("Submission error:", error);
      alert("Something went wrong. Please try again.");
    });
  });
});
