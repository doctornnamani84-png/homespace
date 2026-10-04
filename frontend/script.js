const API_BASE = "/api";

// ---- Simple state, kept in memory + localStorage for persistence ----
let currentUser = JSON.parse(localStorage.getItem("homespace_user") || "null");
let accessToken = localStorage.getItem("homespace_token") || null;
const propertiesById = new Map();

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

  if (currentUser.role === "tenant") {
    document.getElementById("my-bookings-section").classList.remove("hidden");
    loadMyBookings();
  }
}

function setLoggedOutUI() {
  btnShowLogin.classList.remove("hidden");
  btnShowRegister.classList.remove("hidden");
  btnLogout.classList.add("hidden");
  welcomeMessage.classList.add("hidden");
  createPropertySection.classList.add("hidden");
  document.getElementById("block-dates-section").classList.add("hidden");
  document.getElementById("upload-image-section").classList.add("hidden");
  document.getElementById("upload-video-section").classList.add("hidden");
  document.getElementById("admin-section").classList.add("hidden");
  document.getElementById("my-bookings-section").classList.add("hidden");
  document.getElementById("edit-property-section").classList.add("hidden");
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

    if (response.status === 429) {
      showMessage("login-message", "Too many login attempts. Please wait a moment and try again.", "error");
      return;
    }

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

  const params = new URLSearchParams();
  const locationFilter = location || document.getElementById("filter-location").value.trim();
  const selectedType = document.getElementById("filter-type").value;
  const minPrice = document.getElementById("filter-min-price").value;
  const maxPrice = document.getElementById("filter-max-price").value;
  if (locationFilter) params.set("location", locationFilter);
  if (selectedType === "short_let") {
    params.set("listing_type", "rent");
    params.set("is_short_let", "true");
  } else if (selectedType === "rent") {
    params.set("listing_type", "rent");
    params.set("is_short_let", "false");
  } else if (selectedType === "sale") {
    params.set("listing_type", "sale");
  }
  if (minPrice) params.set("min_price", minPrice);
  if (maxPrice) params.set("max_price", maxPrice);
  const url = `${API_BASE}/properties${params.size ? `?${params}` : ""}`;

  try {
    const response = await fetch(url);
    const data = await response.json();

    if (!response.ok || data.count === 0) {
      propertiesById.clear();
      listEl.innerHTML = "<p>No properties found.</p>";
      return;
    }

    propertiesById.clear();
    data.properties.forEach((property) => propertiesById.set(property.id, property));
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
        ${imgData.images.slice(0, 4).map(img => `
          <div style="position:relative;">
            <img src="${img.image_url}" alt="${escapeHtml(prop.title)}">
            ${canEdit ? `<button onclick="deleteImage(${img.id})" style="position:absolute;top:2px;right:2px;background:#c0392b;color:#fff;border:none;border-radius:50%;width:20px;height:20px;font-size:12px;cursor:pointer;">×</button>` : ""}
          </div>
        `).join("")}
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
      videoHtml = `
        <div class="property-videos">
          ${vidData.videos.map((video, index) => `
            <div class="property-video-item">
              <a href="${escapeHtml(video.video_url)}" target="_blank" rel="noopener noreferrer" class="video-link">Watch video tour ${index + 1}</a>
              ${canEdit ? `<button type="button" class="video-delete-button" onclick="deleteVideo(${video.id})" aria-label="Delete video tour ${index + 1}" title="Delete video tour">Delete</button>` : ""}
            </div>
          `).join("")}
        </div>
      `;
    }
  } catch (err) {
    // If video fails to load, just show the card without it.
  }

const actionButton = prop.listing_type === "sale" || !prop.is_short_let
  ? `<a href="https://wa.me/2348153191672?text=${encodeURIComponent('Hi, I am interested in ' + prop.title + ' listed on HomeSpace')}" target="_blank" rel="noopener noreferrer" class="contact-seller-btn">Enquire about this property</a>`
  : `<button onclick="bookProperty(${prop.id})">Choose dates</button>`;

  const editButton = canEdit
    ? `<button class="edit-btn" onclick='openEditForm(${JSON.stringify(prop)})'>Edit</button>`
    : "";

    const deleteButton = (currentUser && currentUser.role === "admin")
    ? `<button class="delete-btn" onclick="deleteProperty(${prop.id})">Delete</button>`
    : "";

  return `
    <div class="property-card">
      ${imagesHtml}
      <h3>${escapeHtml(prop.title)}</h3>
      ${canEdit ? `<div style="font-size:0.8rem;color:#888;">ID: ${prop.id}</div>` : ""}
      <div class="location">${escapeHtml(prop.location)}</div>
      <div class="price">${priceText}</div>
      ${prop.review_count ? `<p class="property-rating" aria-label="Rated ${prop.average_rating} out of 5 from ${prop.review_count} reviews">★ ${prop.average_rating} <span>(${prop.review_count} verified stay${prop.review_count === 1 ? "" : "s"})</span></p>` : ""}
      <p>${escapeHtml(prop.description || "")}</p>
      ${videoHtml}
      ${actionButton}
      ${editButton}
      ${deleteButton}
    </div>
  `;
}
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// ---- Simple booking action ----

const bookingDialog = document.getElementById("booking-dialog");
const bookingForm = document.getElementById("booking-checkout-form");
let activeBookingPropertyId = null;
let bookingQuote = null;
let quotedDateRange = "";
let quoteRequestNumber = 0;

function formatNaira(amount) {
  return new Intl.NumberFormat("en-NG", {
    style: "currency",
    currency: "NGN",
    maximumFractionDigits: 2,
  }).format(amount);
}

function bookProperty(propertyId) {
  if (!accessToken) {
    alert("Please log in as a tenant to book a property.");
    return;
  }

  const property = propertiesById.get(propertyId);
  if (!property || !property.is_short_let) return;
  activeBookingPropertyId = propertyId;
  bookingQuote = null;
  quotedDateRange = "";
  document.getElementById("booking-dialog-title").textContent = property.title;
  document.getElementById("booking-property-info").textContent = `${property.location} · ${formatNaira(property.price_per_night)} per night · 5% platform fee`;
  document.getElementById("booking-quote").textContent = "Choose your dates to see the total.";
  document.getElementById("booking-message").textContent = "";
  document.getElementById("booking-submit").disabled = true;
  const today = new Date();
  const localToday = new Date(today.getTime() - today.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  document.getElementById("booking-start-date").min = localToday;
  document.getElementById("booking-end-date").min = localToday;
  bookingDialog.showModal();
}

async function refreshBookingQuote() {
  const startDate = document.getElementById("booking-start-date").value;
  const endDate = document.getElementById("booking-end-date").value;
  const dateRange = `${startDate}|${endDate}`;
  const requestNumber = ++quoteRequestNumber;
  bookingQuote = null;
  quotedDateRange = "";
  document.getElementById("booking-submit").disabled = true;

  if (!startDate || !endDate) {
    document.getElementById("booking-quote").textContent = "Choose your dates to see the total.";
    return;
  }

  document.getElementById("booking-quote").textContent = "Checking availability and price...";
  const params = new URLSearchParams({
    property_id: String(activeBookingPropertyId),
    start_date: startDate,
    end_date: endDate,
  });

  try {
    const response = await fetch(`${API_BASE}/bookings/quote?${params}`);
    const data = await response.json();
    if (requestNumber !== quoteRequestNumber) return;
    if (!response.ok) {
      document.getElementById("booking-quote").textContent = data.error || "Could not quote these dates.";
      return;
    }

    bookingQuote = data.quote;
    quotedDateRange = dateRange;
    document.getElementById("booking-quote").textContent =
      `${bookingQuote.nights} night${bookingQuote.nights === 1 ? "" : "s"}\n` +
      `Stay: ${formatNaira(bookingQuote.subtotal)}\n` +
      `5% platform fee: ${formatNaira(bookingQuote.platform_fee)}\n` +
      `Total: ${formatNaira(bookingQuote.total)}`;
    document.getElementById("booking-submit").disabled = false;
  } catch (err) {
    if (requestNumber === quoteRequestNumber) {
      document.getElementById("booking-quote").textContent = "Could not reach the server.";
    }
  }
}

document.getElementById("booking-start-date").addEventListener("change", () => {
  const startDate = document.getElementById("booking-start-date").value;
  const endInput = document.getElementById("booking-end-date");
  endInput.min = startDate || endInput.min;
  if (endInput.value && endInput.value <= startDate) endInput.value = "";
  refreshBookingQuote();
});
document.getElementById("booking-end-date").addEventListener("change", refreshBookingQuote);
document.getElementById("close-booking-dialog").addEventListener("click", () => bookingDialog.close());

bookingForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const startDate = document.getElementById("booking-start-date").value;
  const endDate = document.getElementById("booking-end-date").value;
  if (quotedDateRange !== `${startDate}|${endDate}` || !bookingQuote) {
    await refreshBookingQuote();
    if (quotedDateRange !== `${startDate}|${endDate}` || !bookingQuote) return;
  }

  const submitButton = document.getElementById("booking-submit");
  submitButton.disabled = true;
  document.getElementById("booking-message").textContent = "Creating your booking...";

  try {
    const bookingResponse = await fetch(`${API_BASE}/bookings`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${accessToken}`,
      },
      body: JSON.stringify({
        property_id: activeBookingPropertyId,
        start_date: startDate,
        end_date: endDate,
      }),
    });
    const bookingData = await bookingResponse.json();

    if (!bookingResponse.ok) {
      document.getElementById("booking-message").textContent = bookingData.error || "Booking failed.";
      return;
    }

    const bookingId = bookingData.booking.id;
    document.getElementById("booking-message").textContent = "Booking created. Opening secure payment...";

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
      document.getElementById("booking-message").textContent = paymentData.error || "Could not start payment. You can retry from My bookings.";
      loadMyBookings();
      return;
    }

    // Redirect the browser to Paystack's checkout page
    window.location.href = paymentData.authorization_url;

  } catch (err) {
    document.getElementById("booking-message").textContent = "Could not reach the server. You can retry payment from My bookings.";
    loadMyBookings();
  } finally {
    submitButton.disabled = false;
  }
});

// ---- Filter button ----

document.getElementById("btn-filter").addEventListener("click", () => {
  loadProperties();
});

document.getElementById("filter-location").addEventListener("keydown", (event) => {
  if (event.key === "Enter") loadProperties();
});

// ---- Initial page load ----

if (currentUser && accessToken) {
  setLoggedInUI();
} else {
  setLoggedOutUI();
}

loadProperties();

async function loadMyBookings() {
  const listEl = document.getElementById("my-bookings-list");
  if (!listEl || !accessToken) return;
  listEl.innerHTML = "<p>Loading your bookings...</p>";

  try {
    const response = await fetch(`${API_BASE}/bookings/mine`, {
      headers: { "Authorization": `Bearer ${accessToken}` },
    });
    const data = await response.json();
    if (!response.ok) {
      listEl.textContent = data.error || "Could not load your bookings.";
      return;
    }
    if (data.count === 0) {
      listEl.innerHTML = "<p>You have no bookings yet.</p>";
      return;
    }

    listEl.innerHTML = data.bookings.map((booking) => `
      <article class="guest-booking">
        <div>
          <h3>${escapeHtml(booking.property_title || "Property")}</h3>
          <p>${escapeHtml(booking.property_location || "")}</p>
          <p>${booking.start_date} to ${booking.end_date}</p>
        </div>
        <div class="guest-booking-status">
          <strong>${formatNaira(booking.total_price)}</strong>
          <span>${escapeHtml(booking.status)}</span>
          ${booking.status === "pending" ? `<button type="button" onclick="continuePayment(${booking.id})">Pay now</button>` : ""}
          ${booking.status === "confirmed" && booking.end_date < new Date().toISOString().slice(0, 10) && !booking.review_submitted ? `<form class="review-form" onsubmit="submitBookingReview(event, ${booking.id})"><label>Rate your stay<select name="rating" required><option value="">Rating</option><option value="5">5 - Excellent</option><option value="4">4 - Good</option><option value="3">3 - Okay</option><option value="2">2 - Poor</option><option value="1">1 - Very poor</option></select></label><textarea name="comment" maxlength="1200" placeholder="Share details of your stay" required></textarea><button type="submit">Submit review</button></form>` : booking.review_submitted ? "<span>Review submitted</span>" : ""}
        </div>
      </article>
    `).join("");
  } catch (err) {
    listEl.textContent = "Could not reach the server.";
  }
}

async function continuePayment(bookingId) {
  try {
    const response = await fetch(`${API_BASE}/payments/initialize`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ booking_id: bookingId }),
    });
    const data = await response.json();
    if (!response.ok) {
      alert(data.error || "Could not start payment.");
      return;
    }
    window.location.href = data.authorization_url;
  } catch (err) {
    alert("Could not reach the server.");
  }
}


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

// ---- Upload property video (landlord/admin) ----

document.getElementById("upload-video-form").addEventListener("submit", async (e) => {
  e.preventDefault();

  const propertyId = document.getElementById("upload-video-property-id").value;
  const fileInput = document.getElementById("upload-video-file");
  const file = fileInput.files[0];

  if (!file) {
    showMessage("upload-video-message", "Please select a video file.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("video", file);

  try {
    const response = await fetch(`${API_BASE}/properties/${propertyId}/videos`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${accessToken}`,
      },
      body: formData,
    });
    const data = await response.json();

    if (!response.ok) {
      showMessage("upload-video-message", data.error || "Video upload failed", "error");
      return;
    }

    showMessage("upload-video-message", "Video uploaded successfully!", "success");
    e.target.reset();
    loadProperties();
  } catch (err) {
    showMessage("upload-video-message", "Could not reach the server.", "error");
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

// ---- Delete property (admin only) ----

async function deleteProperty(propertyId) {
  if (!confirm("Are you sure you want to permanently delete this property? This cannot be undone.")) return;

  try {
    const response = await fetch(`${API_BASE}/properties/${propertyId}`, {
      method: "DELETE",
      headers: { "Authorization": `Bearer ${accessToken}` },
    });
    const data = await response.json();

    if (!response.ok) {
      alert(data.error || "Could not delete property");
      return;
    }

    loadProperties();
  } catch (err) {
    alert("Could not reach the server.");
  }
}

async function deleteImage(imageId) {
  if (!confirm("Delete this photo?")) return;
  try {
    const response = await fetch(`${API_BASE}/properties/images/${imageId}`, {
      method: "DELETE",
      headers: { "Authorization": `Bearer ${accessToken}` },
    });
    if (!response.ok) {
      const data = await response.json();
      alert(data.error || "Could not delete photo");
      return;
    }
    loadProperties();
  } catch (err) {
    alert("Could not reach the server.");
  }
}

async function deleteVideo(videoId) {
  if (!confirm("Permanently delete this video tour?")) return;
  try {
    const response = await fetch(`${API_BASE}/properties/videos/${videoId}`, {
      method: "DELETE",
      headers: { "Authorization": `Bearer ${accessToken}` },
    });
    const data = await response.json();
    if (!response.ok) {
      alert(data.error || "Could not delete video");
      return;
    }
    loadProperties();
  } catch (err) {
    alert("Could not reach the server.");
  }
}

async function submitBookingReview(event, bookingId) {
  event.preventDefault();
  const form = event.currentTarget;
  const formData = new FormData(form);
  try {
    const response = await fetch(`${API_BASE}/bookings/${bookingId}/review`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${accessToken}`,
      },
      body: JSON.stringify({
        rating: Number(formData.get("rating")),
        comment: formData.get("comment"),
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      alert(data.error || "Could not submit review.");
      return;
    }
    loadMyBookings();
    loadProperties();
  } catch (err) {
    alert("Could not reach the server.");
  }
}