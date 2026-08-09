const API_BASE = "/api";

// ---- Simple state, kept in memory + localStorage for persistence ----
let currentUser = JSON.parse(localStorage.getItem("homespace_user") || "null");
let accessToken = localStorage.getItem("homespace_token") || null;

// ---- DOM references ----
const loginSection = document.getElementById("login-section");
const registerSection = document.getElementById("register-section");
const createPropertySection = document.getElementById("create-property-section");
const welcomeMessage = document.getElementById("welcome-message");
const btnShowLogin = document.getElementById("btn-show-login");
const btnShowRegister = document.getElementById("btn-show-register");
const btnLogout = document.getElementById("btn-logout");

// ---- Helpers ----

function showMessage(elementId, text, type) {
  const el = document.getElementById(elementId);
  el.textContent = text;
  el.className = `message ${type}`;
}

function setLoggedInUI() {
  loginSection.classList.add("hidden");
  registerSection.classList.add("hidden");
  btnShowLogin.classList.add("hidden");
  btnShowRegister.classList.add("hidden");
  btnLogout.classList.remove("hidden");
  welcomeMessage.classList.remove("hidden");
  welcomeMessage.textContent = `Hi, ${currentUser.name} (${currentUser.role})`;

 if (currentUser.role === "landlord" || currentUser.role === "admin") {
    createPropertySection.classList.remove("hidden");
    document.getElementById("block-dates-section").classList.remove("hidden");
    document.getElementById("upload-image-section").classList.remove("hidden");
    document.getElementById("upload-video-section").classList.remove("hidden");
}

  if (currentUser.role === "admin") {
    document.getElementById("admin-section").classList.remove("hidden");
    loadAdminBookings();
  }
}

function setLoggedOutUI() {
  btnShowLogin.classList.remove("hidden");
  btnShowRegister.classList.remove("hidden");
  btnLogout.classList.add("hidden");
  welcomeMessage.classList.add("hidden");
  createPropertySection.classList.add("hidden");
}

function saveSession(user, token) {
  currentUser = user;
  accessToken = token;
  localStorage.setItem("homespace_user", JSON.stringify(user));
  localStorage.setItem("homespace_token", token);
}

function clearSession() {
  currentUser = null;
  accessToken = null;
  localStorage.removeItem("homespace_user");
  localStorage.removeItem("homespace_token");
}

// ---- Auth: show/hide forms ----

btnShowLogin.addEventListener("click", () => {
  loginSection.classList.toggle("hidden");
  registerSection.classList.add("hidden");
});

btnShowRegister.addEventListener("click", () => {
  registerSection.classList.toggle("hidden");
  loginSection.classList.add("hidden");
});

btnLogout.addEventListener("click", () => {
  clearSession();
  setLoggedOutUI();
});

// ---- Register ----

document.getElementById("register-form").addEventListener("submit", async (e) => {
  e.preventDefault();

  const name = document.getElementById("register-name").value;
  const email = document.getElementById("register-email").value;
  const password = document.getElementById("register-password").value;
  const role = document.getElementById("register-role").value;

  try {
    const response = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, email, password, role }),
    });
    const data = await response.json();

    if (!response.ok) {
      showMessage("register-message", data.error || "Registration failed", "error");
      return;
    }

    showMessage("register-message", "Account created! You can now log in.", "success");
    e.target.reset();
  } catch (err) {
    showMessage("register-message", "Could not reach the server.", "error");
  }
});

// ---- Login ----

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();

  const email = document.getElementById("login-email").value;
  const password = document.getElementById("login-password").value;

  try {
    const response = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await response.json();

    if (!response.ok) {
      showMessage("login-message", data.error || "Login failed", "error");
      return;
    }

    saveSession(data.user, data.access_token);
    setLoggedInUI();
    showMessage("login-message", "", "");
    e.target.reset();
  } catch (err) {
    showMessage("login-message", "Could not reach the server.", "error");
  }
});

// ---- Create property (landlord only) ----

document.getElementById("create-property-form").addEventListener("submit", async (e) => {
  e.preventDefault();

  const title = document.getElementById("prop-title").value;
  const description = document.getElementById("prop-description").value;
  const location = document.getElementById("prop-location").value;
  const isShortLet = document.getElementById("prop-is-short-let").checked;
  const pricePerNight = document.getElementById("prop-price-per-night").value;
  const monthlyRent = document.getElementById("prop-monthly-rent").value;
  const videoUrl = document.getElementById("prop-video-url").value;
  const listingType = document.getElementById("prop-listing-type").value;

  try {
    const response = await fetch(`${API_BASE}/properties`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${accessToken}`,
      },
      body: JSON.stringify({
        title,
        description,
        location,
        is_short_let: isShortLet,
        price_per_night: pricePerNight ? Number(pricePerNight) : null,
        monthly_rent: monthlyRent ? Number(monthlyRent) : null,
        video_url: videoUrl || null,
        listing_type: listingType,
      }),
    });
    const data = await response.json();

    if (!response.ok) {
      showMessage("create-property-message", data.error || "Could not list property", "error");
      return;
    }

    showMessage("create-property-message", "Property listed successfully!", "success");
    e.target.reset();
    loadProperties();
  } catch (err) {
    showMessage("create-property-message", "Could not reach the server.", "error");
  }
});

// ---- Load & display properties ----

async function loadProperties(location) {
  const listEl = document.getElementById("properties-list");
  listEl.innerHTML = "<p>Loading...</p>";

  let url = `${API_BASE}/properties`;
  if (location) {
    url += `?location=${encodeURIComponent(location)}`;
  }

  try {
    const response = await fetch(url);
    const data = await response.json();

    if (!response.ok || data.count === 0) {
      listEl.innerHTML = "<p>No properties found.</p>";
      return;
    }

    const cardsHtml = await Promise.all(data.properties.map(renderPropertyCard));
    listEl.innerHTML = cardsHtml.join("");
  } catch (err) {
    listEl.innerHTML = "<p>Could not load properties.</p>";
  }
}

async function renderPropertyCard(prop) {
  const canEdit = currentUser && (currentUser.role === "admin" || currentUser.id === prop.landlord_id);
  let priceText;
  
  if (prop.listing_type === "sale") {
    priceText = `₦${Number(prop.monthly_rent).toLocaleString()} (For Sale)`;
  } else if (prop.is_short_let) {
    priceText = `₦${Number(prop.price_per_night).toLocaleString()} / night`;
  } else {
    priceText = `₦${Number(prop.monthly_rent).toLocaleString()} / month`;
  }

  let imagesHtml = "";
  try {
    const imgResponse = await fetch(`${API_BASE}/properties/${prop.id}/images`);
    const imgData = await imgResponse.json();

    if (imgData.count > 0) {
      imagesHtml = `
        <div class="property-gallery">
          ${imgData.images.slice(0, 4).map(img => `<img src="${img.image_url}" alt="${escapeHtml(prop.title)}">`).join("")}
        </div>
      `;
    }
  } catch (err) {
    // If images fail to load, just show the card without a gallery.
  }

  let videoHtml = "";
  try {
    const vidResponse = await fetch(`${API_BASE}/properties/${prop.id}/videos`);
    const vidData = await vidResponse.json();

    if (vidData.count > 0) {
      videoHtml = `<a href="${escapeHtml(vidData.videos[0].video_url)}" target="_blank" class="video-link">🎥 Watch Video Tour</a>`;
    }
  } catch (err) {
    // If video fails to load, just show the card without it.
  }

const actionButton = prop.listing_type === "sale"
    ? `<a href="https://wa.me/2348153191672?text=${encodeURIComponent('Hi, I am interested in ' + prop.title + ' listed on HomeSpace')}" target="_blank" class="contact-seller-btn">Contact Us About This Property</a>`
    : `<button onclick="bookProperty(${prop.id})">Book Now</button>`;

  const editButton = canEdit
    ? `<button class="edit-btn" onclick='openEditForm(${JSON.stringify(prop)})'>Edit</button>`
    : "";

  return `
    <div class="property-card">
      ${imagesHtml}
      <h3>${escapeHtml(prop.title)}</h3>
      <div class="location">${escapeHtml(prop.location)}</div>
      <div class="price">${priceText}</div>
      <p>${escapeHtml(prop.description || "")}</p>
      ${videoHtml}
      ${actionButton}
      ${editButton}
    </div>
  `;
}
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// ---- Simple booking action ----

async function bookProperty(propertyId) {
  if (!accessToken) {
    alert("Please log in as a tenant to book a property.");
    return;
  }

  const startDate = prompt("Start date (YYYY-MM-DD):");
  const endDate = prompt("End date (YYYY-MM-DD):");
  if (!startDate || !endDate) return;

  try {
    const bookingResponse = await fetch(`${API_BASE}/bookings`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${accessToken}`,
      },
      body: JSON.stringify({
        property_id: propertyId,
        start_date: startDate,
        end_date: endDate,
      }),
    });
    const bookingData = await bookingResponse.json();

    if (!bookingResponse.ok) {
      alert(bookingData.error || "Booking failed");
      return;
    }

    const bookingId = bookingData.booking.id;
    alert(`Booking created! Total: ₦${Number(bookingData.booking.total_price).toLocaleString()}\nRedirecting to payment...`);

    const paymentResponse = await fetch(`${API_BASE}/payments/initialize`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ booking_id: bookingId }),
    });
    const paymentData = await paymentResponse.json();

    if (!paymentResponse.ok) {
      alert(paymentData.error || "Could not start payment");
      return;
    }

    // Redirect the browser to Paystack's checkout page
    window.location.href = paymentData.authorization_url;

  } catch (err) {
    alert("Could not reach the server.");
  }
}

// ---- Filter button ----

document.getElementById("btn-filter").addEventListener("click", () => {
  const location = document.getElementById("filter-location").value;
  loadProperties(location);
});

// ---- Initial page load ----

if (currentUser && accessToken) {
  setLoggedInUI();
} else {
  setLoggedOutUI();
}

loadProperties();


// ---- Admin: load and display all bookings ----

async function loadAdminBookings() {
  const listEl = document.getElementById("admin-bookings-list");
  listEl.innerHTML = "<p>Loading...</p>";

  try {
    const response = await fetch(`${API_BASE}/bookings/all`, {
      headers: { "Authorization": `Bearer ${accessToken}` },
    });
    const data = await response.json();

    if (!response.ok) {
      listEl.innerHTML = `<p>${data.error || "Could not load bookings."}</p>`;
      return;
    }

    if (data.count === 0) {
      listEl.innerHTML = "<p>No bookings yet.</p>";
      return;
    }

    listEl.innerHTML = `
      <table class="admin-table">
      <thead>
        <tr>
          <th>Property</th>
          <th>Tenant</th>
          <th>Dates</th>
          <th>Price</th>
          <th>Status</th>
          <th>Payout</th>
          <th>Action</th>
        </tr>
      </thead>
        <tbody>
          ${data.bookings.map(renderAdminBookingRow).join("")}
        </tbody>
      </table>
    `;
  } catch (err) {
    listEl.innerHTML = "<p>Could not reach the server.</p>";
  }
}

function renderAdminBookingRow(booking) {
  const canCancel = booking.status !== "cancelled";
  const cancelCell = canCancel
    ? `<button onclick="cancelBooking(${booking.id})">Cancel</button>`
    : `<em>Cancelled</em>`;

  let payoutCell;
  if (booking.status !== "confirmed") {
    payoutCell = `<span class="payout-na">N/A</span>`;
  } else if (booking.payout_status === "paid_out") {
    payoutCell = `<span class="payout-done">✅ Paid Out</span>`;
  } else {
    payoutCell = `<button class="payout-btn" onclick="markPaidOut(${booking.id})">Mark Paid Out</button>`;
  }

  return `
    <tr>
      <td>${escapeHtml(booking.property_title || "")}</td>
      <td>${escapeHtml(booking.tenant_name || "")} (${escapeHtml(booking.tenant_email || "")})</td>
      <td>${booking.start_date} → ${booking.end_date}</td>
      <td>₦${Number(booking.total_price).toLocaleString()}</td>
      <td>${escapeHtml(booking.status)}</td>
      <td>${payoutCell}</td>
      <td>${cancelCell}</td>
    </tr>
  `;
}

async function cancelBooking(bookingId) {
  if (!confirm("Cancel this booking?")) return;

  try {
    const response = await fetch(`${API_BASE}/bookings/${bookingId}/cancel`, {
      method: "PATCH",
      headers: { "Authorization": `Bearer ${accessToken}` },
    });
    const data = await response.json();

    if (!response.ok) {
      alert(data.error || "Could not cancel booking");
      return;
    }

    loadAdminBookings();
  } catch (err) {
    alert("Could not reach the server.");
  }
}

async function markPaidOut(bookingId) {
  if (!confirm("Confirm you have manually paid the landlord their share for this booking?")) return;

  try {
    const response = await fetch(`${API_BASE}/bookings/${bookingId}/mark-paid-out`, {
      method: "PATCH",
      headers: { "Authorization": `Bearer ${accessToken}` },
    });
    const data = await response.json();

    if (!response.ok) {
      alert(data.error || "Could not mark as paid out");
      return;
    }

    loadAdminBookings();
  } catch (err) {
    alert("Could not reach the server.");
  }
}

// ---- Block dates (landlord/admin) ----

document.getElementById("block-dates-form").addEventListener("submit", async (e) => {
  e.preventDefault();

  const propertyId = document.getElementById("block-property-id").value;
  const startDate = document.getElementById("block-start-date").value;
  const endDate = document.getElementById("block-end-date").value;
  const reason = document.getElementById("block-reason").value;

  try {
    const response = await fetch(`${API_BASE}/properties/${propertyId}/block`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ start_date: startDate, end_date: endDate, reason }),
    });
    const data = await response.json();

    if (!response.ok) {
      showMessage("block-dates-message", data.error || "Could not block dates", "error");
      return;
    }

    showMessage("block-dates-message", "Dates blocked successfully!", "success");
    e.target.reset();
  } catch (err) {
    showMessage("block-dates-message", "Could not reach the server.", "error");
  }
});

// ---- Upload property image (landlord/admin) ----

document.getElementById("upload-image-form").addEventListener("submit", async (e) => {
  e.preventDefault();

  const propertyId = document.getElementById("upload-property-id").value;
  const fileInput = document.getElementById("upload-image-file");
  const file = fileInput.files[0];

  if (!file) {
    showMessage("upload-image-message", "Please select a file.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("image", file);

  try {
    const response = await fetch(`${API_BASE}/properties/${propertyId}/images`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${accessToken}`,
        // Note: no "Content-Type" header here — the browser sets it
        // automatically for FormData, including the required boundary.
      },
      body: formData,
    });
    const data = await response.json();

    if (!response.ok) {
      showMessage("upload-image-message", data.error || "Upload failed", "error");
      return;
    }

    showMessage("upload-image-message", "Photo uploaded successfully!", "success");
    e.target.reset();
    loadProperties();
  } catch (err) {
    showMessage("upload-image-message", "Could not reach the server.", "error");
  }
});

// ---- Edit property (owner landlord or admin) ----

function openEditForm(prop) {
  document.getElementById("edit-prop-id").value = prop.id;
  document.getElementById("edit-prop-listing-type").value = prop.listing_type || "rent";
  document.getElementById("edit-prop-title").value = prop.title;
  document.getElementById("edit-prop-description").value = prop.description || "";
  document.getElementById("edit-prop-location").value = prop.location;
  document.getElementById("edit-prop-is-short-let").checked = prop.is_short_let;
  document.getElementById("edit-prop-price-per-night").value = prop.price_per_night || "";
  document.getElementById("edit-prop-monthly-rent").value = prop.monthly_rent || "";

  document.getElementById("edit-property-section").classList.remove("hidden");
  document.getElementById("edit-property-section").scrollIntoView({ behavior: "smooth" });
}

document.getElementById("btn-cancel-edit").addEventListener("click", () => {
  document.getElementById("edit-property-section").classList.add("hidden");
});

document.getElementById("edit-property-form").addEventListener("submit", async (e) => {
  e.preventDefault();

  const propertyId = document.getElementById("edit-prop-id").value;
  const listingType = document.getElementById("edit-prop-listing-type").value;
  const title = document.getElementById("edit-prop-title").value;
  const description = document.getElementById("edit-prop-description").value;
  const location = document.getElementById("edit-prop-location").value;
  const isShortLet = document.getElementById("edit-prop-is-short-let").checked;
  const pricePerNight = document.getElementById("edit-prop-price-per-night").value;
  const monthlyRent = document.getElementById("edit-prop-monthly-rent").value;

  try {
    const response = await fetch(`${API_BASE}/properties/${propertyId}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${accessToken}`,
      },
      body: JSON.stringify({
        title,
        description,
        location,
        is_short_let: isShortLet,
        price_per_night: pricePerNight ? Number(pricePerNight) : null,
        monthly_rent: monthlyRent ? Number(monthlyRent) : null,
        listing_type: listingType,
      }),
    });
    const data = await response.json();

    if (!response.ok) {
      showMessage("edit-property-message", data.error || "Could not update property", "error");
      return;
    }

    showMessage("edit-property-message", "Property updated successfully!", "success");
    document.getElementById("edit-property-section").classList.add("hidden");
    loadProperties();
  } catch (err) {
    showMessage("edit-property-message", "Could not reach the server.", "error");
  }
});