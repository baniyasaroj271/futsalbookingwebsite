document.addEventListener("DOMContentLoaded", () => {
  const mapConfig = window.mapConfig || {
    tileUrl: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  };
  const addTiles = (map) => L.tileLayer(mapConfig.tileUrl, {
    attribution: mapConfig.attribution,
  }).addTo(map);
  const toggle = document.querySelector(".menu-toggle");
  const links = document.querySelector(".nav-links");
  if (toggle) toggle.addEventListener("click", () => links.classList.toggle("open"));

  const mapElement = document.getElementById("venue-map");
  if (mapElement && window.venueData?.length) {
    const map = L.map(mapElement).setView([27.7172, 85.324], 11);
    addTiles(map);
    window.venueData.forEach((venue) => {
      L.marker(venue.coordinates).addTo(map).bindPopup(venue.name);
    });
  }
  const detailMapElement = document.getElementById("detail-map");
  if (detailMapElement && window.detailVenue) {
    const detailMap = L.map(detailMapElement).setView(
      [window.detailVenue.latitude, window.detailVenue.longitude],
      15,
    );
    addTiles(detailMap);
    L.marker([window.detailVenue.latitude, window.detailVenue.longitude])
      .addTo(detailMap)
      .bindPopup(window.detailVenue.name)
      .openPopup();
  }

  const searchPage = document.querySelector(".search-page");
  if (!searchPage) return;
  const results = document.getElementById("venue-results");
  const searchMapElement = document.getElementById("search-map");
  const searchInput = document.getElementById("venue-search");
  const message = document.getElementById("location-message");
  const state = { latitude: 27.7172, longitude: 85.3240, hasLocation: false, view: "list" };
  const venues = (window.searchVenues || []).map((venue) => ({ ...venue, distance: venue.distance ?? null }));
  const calculateDistance = (lat1, lon1, lat2, lon2) => {
    const earthRadius = 6371.0088;
    const radians = (degrees) => degrees * Math.PI / 180;
    const dLat = radians(lat2 - lat1);
    const dLon = radians(lon2 - lon1);
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(radians(lat1)) * Math.cos(radians(lat2)) * Math.sin(dLon / 2) ** 2;
    return earthRadius * 2 * Math.asin(Math.sqrt(a));
  };
  const map = L.map(searchMapElement).setView([state.latitude, state.longitude], 12);
  addTiles(map);
  let markers = [];
  const render = () => {
    const query = window.areaSearch ? "" : searchInput.value.trim().toLowerCase();
    const sortBy = document.getElementById("sort-by").value;
    const openOnly = document.getElementById("open-only").checked;
    const availableOnly = document.getElementById("available-only").checked;
    const filtered = venues.filter((venue) => (!query || `${venue.name} ${venue.location}`.toLowerCase().includes(query)) && (!openOnly || venue.is_open) && (!availableOnly || venue.available_slots > 0));
    filtered.sort((a, b) => (sortBy === "price" ? a.price - b.price : sortBy === "rating" ? b.rating - a.rating : (a.distance ?? 9999) - (b.distance ?? 9999)));
    document.getElementById("result-count").textContent = filtered.length;
    results.innerHTML = filtered.length ? filtered.map((venue) => `<article class="search-result-card"><img src="${venue.image_url}" alt="${venue.name}"><div class="search-result-body"><div class="venue-title-row"><h3>${venue.name}</h3><span class="rating">★ ${venue.rating}</span></div><p class="muted">⌖ ${venue.location} · <strong>${venue.distance === null ? "Set location" : `${venue.distance.toFixed(1)} km`}</strong></p><div class="search-result-meta"><strong>रु ${venue.price.toLocaleString()}<small>/hr</small></strong><span class="${venue.is_open ? "availability" : "unavailable"}">● ${venue.is_open ? `${venue.available_slots} slots available` : "Closed"}</span><a class="button button-small" href="/venues/${venue.slug}">View pitch</a></div></div></article>`).join("") : `<div class="empty-card"><h3>No futsals match your search.</h3><p class="muted">Try a different name, location, or filter.</p></div>`;
    markers.forEach((marker) => marker.remove());
    markers = filtered.map((venue) => L.marker([venue.latitude, venue.longitude]).addTo(map).bindPopup(`<strong>${venue.name}</strong><br>${venue.distance === null ? "Distance unavailable" : `${venue.distance.toFixed(1)} km away`}`));
  };
  const setLocation = (latitude, longitude, label) => {
    state.latitude = latitude; state.longitude = longitude; state.hasLocation = true;
    venues.forEach((venue) => { venue.distance = calculateDistance(latitude, longitude, venue.latitude, venue.longitude); });
    message.textContent = `Showing distances from ${label}.`;
    map.setView([latitude, longitude], 12);
    render();
  };
  document.getElementById("use-location").addEventListener("click", () => {
    if (!navigator.geolocation) { message.textContent = "Geolocation is unavailable. Choose an area manually."; return; }
    message.textContent = "Requesting your location…";
    navigator.geolocation.getCurrentPosition((position) => setLocation(position.coords.latitude, position.coords.longitude, "your location"), () => { message.textContent = "Location permission was denied. Choose an area manually."; });
  });
  document.getElementById("manual-location").addEventListener("change", (event) => {
    if (!event.target.value) return;
    const [latitude, longitude] = event.target.value.split(",").map(Number);
    setLocation(latitude, longitude, event.target.options[event.target.selectedIndex].text);
  });
  document.getElementById("search-submit").addEventListener("click", render);
  ["sort-by", "open-only", "available-only"].forEach((id) => document.getElementById(id).addEventListener("change", render));
  document.querySelectorAll(".view-toggle").forEach((button) => button.addEventListener("click", () => {
    state.view = button.dataset.view;
    document.querySelectorAll(".view-toggle").forEach((item) => item.classList.toggle("active", item === button));
    searchMapElement.classList.toggle("visible", state.view === "map");
    results.classList.toggle("hidden", state.view === "map");
    setTimeout(() => map.invalidateSize(), 50);
  }));
  render();
});
