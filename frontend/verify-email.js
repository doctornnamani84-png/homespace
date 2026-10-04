const verificationMessage = document.getElementById("verification-message");
const verifyButton = document.getElementById("verify-email-button");
const returnHomeLink = document.getElementById("return-home-link");
const verificationToken = new URLSearchParams(window.location.search).get("token");

verifyButton.addEventListener("click", async () => {
  if (!verificationToken) {
    verificationMessage.textContent = "This link is missing its token. Request a new verification email from the login form.";
    verifyButton.disabled = true;
    return;
  }

  verifyButton.disabled = true;
  verificationMessage.textContent = "Verifying your email...";
  try {
    const response = await fetch("/api/auth/verify-email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: verificationToken }),
    });
    const data = await response.json();
    verificationMessage.textContent = data.message || data.error || "Could not verify this link.";
    if (response.ok) {
      verifyButton.classList.add("hidden");
      returnHomeLink.classList.remove("hidden");
    } else {
      verifyButton.disabled = false;
    }
  } catch (err) {
    verificationMessage.textContent = "Could not reach HomeSpace. Please try again.";
    verifyButton.disabled = false;
  }
});