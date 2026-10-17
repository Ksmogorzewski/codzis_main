const TABS = ["ogloszenia", "dodaj", "profil", "platnosci"];
const $ = (id) => document.getElementById(id);

let profile = null;

// --- UI helpers ---

let toastTimer;
function toast(text, kind = "ok") {
  const node = $("toast");
  node.textContent = text;
  node.className = `toast ${kind}`;
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (node.hidden = true), 4000);
}

function setStatus(node, text, kind = "") {
  node.textContent = text;
  node.className = `status ${kind}`;
}

// Tagi z taggera AI: {theme: [...], audience: "...", format: [...], cost: "...", mode: "..."}
const tagList = (tags) => Object.values(tags || {}).flat().filter(Boolean);

function parseHash() {
  const [tab, query] = location.hash.slice(1).split("?");
  return { tab: TABS.includes(tab) ? tab : "ogloszenia", params: new URLSearchParams(query) };
}

function renderPackages(container, onBuy) {
  container.replaceChildren(
    ...sortedPackages().map((p) => {
      const action = onBuy
        ? el("button", { className: "primary", type: "button", textContent: "Kup", onclick: (e) => onBuy(p, e.target) })
        : el("a", { className: "button", href: "#", textContent: "Zaloguj się, aby kupić", onclick: focusLogin });
      return el(
        "div",
        { className: "card package" },
        el("h3", { textContent: p.name }),
        el("div", { className: "price", textContent: formatMoney(p.price) }),
        el("div", { className: "muted", textContent: `${creditsLabel(p.credits)} · ${formatMoney(p.price / p.credits)} / kredyt` }),
        el("div", { className: "spacer" }),
        action,
      );
    }),
  );
}

function focusLogin(e) {
  e.preventDefault();
  $("login-form").scrollIntoView({ behavior: "smooth" });
  $("login-form").apiKey.focus();
}

// --- sesja ---

async function refreshProfile() {
  profile = await api("GET", "/me");
  $("credits-pill").textContent = creditsLabel(profile.credits);
  return profile;
}

async function login(key) {
  profile = await api("GET", "/me", null, key);
  session.set(key);
  await render();
}

function logout(message) {
  session.set(null);
  profile = null;
  history.replaceState(null, "", location.pathname);
  render();
  if (message) toast(message, "error");
}

function handleError(err) {
  if (err.status === 403) return logout("Sesja wygasła lub klucz został unieważniony.");
  toast(err.message, "error");
}

// --- widoki ---

const VIEWS = {
  async ogloszenia() {
    const list = $("events-list");
    list.replaceChildren(el("p", { className: "muted", textContent: "Ładowanie…" }));
    const { items } = await api("GET", "/events");
    $("events-empty").hidden = items.length > 0;
    list.replaceChildren(
      ...items.map((ev) => {
        const photo = el("div", { className: "photo" });
        const img = el("img", { src: ev.imageUrl || "", alt: "", loading: "lazy" });
        img.onerror = () => photo.replaceChildren("Brak zdjęcia");
        photo.append(img);
        const where = [ev.venue?.name, ev.district].filter(Boolean).join(" · ");
        return el(
          "article",
          { className: "card event" },
          photo,
          el(
            "div",
            { className: "body" },
            el(
              "div",
              { className: "badges" },
              el("span", { className: `badge ${ev.status}`, textContent: SUBMISSION_STATUS[ev.status] || ev.status }),
              el("span", { className: "badge", textContent: ev.category?.[0]?.name || "" }),
            ),
            el("h3", { textContent: ev.title }),
            el("div", { className: "muted small", textContent: formatDate(ev.occurrences?.[0]?.start || ev.startsAt) }),
            el("div", { className: "muted small", textContent: where }),
            el("p", { className: "lead-text", textContent: ev.lead || "" }),
            tagList(ev.tags).length ? el("div", { className: "tags" }, ...tagList(ev.tags).map((t) => el("span", { textContent: t }))) : null,
          ),
        );
      }),
    );
  },

  async dodaj() {
    const { credits, eventCost } = await refreshProfile();
    const enough = credits >= eventCost;
    const notice = $("new-cost");
    notice.replaceChildren(
      `Publikacja kosztuje ${creditsLabel(eventCost)}. Masz ${creditsLabel(credits)}.`,
      enough ? "" : " ",
      enough ? "" : el("a", { href: "#platnosci", textContent: "Kup kredyty" }),
    );
    $("event-form").querySelector("button[type=submit]").disabled = !enough;
  },

  async profil() {
    const { partnerName, partnerId, credits, eventCost } = await refreshProfile();
    $("profile-name").textContent = partnerName;
    $("profile-id").textContent = partnerId;
    $("profile-credits").textContent = credits;
    $("profile-capacity").textContent = `Wystarczy na ${plural(Math.floor(credits / eventCost), "ogłoszenie", "ogłoszenia", "ogłoszeń")}`;
  },

  async platnosci(params) {
    const status = params.get("status");
    if (status) {
      history.replaceState(null, "", "#platnosci");
      if (status === "paid") toast("Płatność zakończona, kredyty dodane.");
      if (status === "cancelled") toast("Płatność anulowana.", "error");
    }

    renderPackages($("portal-packages"), buyPackage);
    const [{ items }] = await Promise.all([api("GET", "/payments"), refreshProfile()]);
    $("payments-empty").hidden = items.length > 0;
    $("payments-list").replaceChildren(
      ...items.map((p) =>
        el(
          "tr",
          {},
          el("td", { textContent: formatDate(p.createdAt) }),
          el("td", { textContent: p.packageName }),
          el("td", { textContent: p.credits }),
          el("td", { textContent: formatMoney(p.amount, p.currency) }),
          el(
            "td",
            {},
            el("span", { className: `badge ${p.status}`, textContent: PAYMENT_STATUS[p.status] || p.status }),
            p.status === "pending" ? el("a", { href: `mock-pay.html?id=${p.id}`, textContent: " dokończ", className: "small" }) : null,
          ),
        ),
      ),
    );
  },
};

async function buyPackage(pkg, button) {
  button.disabled = true;
  try {
    const payment = await api("POST", "/payments", { package: pkg.id });
    location.assign(payment.redirectUrl);
  } catch (err) {
    button.disabled = false;
    handleError(err);
  }
}

async function render() {
  const loggedIn = Boolean(session.get() && profile);
  $("landing").hidden = loggedIn;
  $("portal").hidden = !loggedIn;
  $("nav").hidden = !loggedIn;
  $("account").hidden = !loggedIn;

  if (!loggedIn) {
    $("landing-cost").textContent = `${creditsLabel(CONFIG.eventCost)} za ogłoszenie`;
    renderPackages($("landing-packages"));
    return;
  }

  $("credits-pill").textContent = creditsLabel(profile.credits);
  const { tab, params } = parseHash();
  document.querySelectorAll("[data-view]").forEach((v) => (v.hidden = v.dataset.view !== tab));
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.hash === `#${tab}`));

  try {
    await VIEWS[tab](params);
  } catch (err) {
    handleError(err);
  }
}

// --- formularze ---

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const button = form.querySelector("button");
  button.disabled = true;
  setStatus($("login-status"), "Logowanie…");
  try {
    await login(new FormData(form).get("apiKey").trim());
    form.reset();
    setStatus($("login-status"), "");
  } catch (err) {
    session.set(null);
    setStatus($("login-status"), err.message, "error");
  } finally {
    button.disabled = false;
  }
});

$("event-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const statusNode = $("event-status");

  const data = new FormData(form);
  const photo = data.get("photo");
  data.delete("photo");

  if (!photo || !photo.size) return setStatus(statusNode, "Wybierz zdjęcie.", "error");
  if (photo.size > CONFIG.maxPhotoMb * 1024 * 1024) {
    return setStatus(statusNode, `Zdjęcie jest za duże (max ${CONFIG.maxPhotoMb} MB).`, "error");
  }

  const payload = Object.fromEntries(data.entries());
  payload.startsAt = withTimezone(payload.startsAt);
  if (payload.endsAt) payload.endsAt = withTimezone(payload.endsAt);
  else delete payload.endsAt;
  payload.photoContentType = photo.type;

  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  setStatus(statusNode, "Wysyłanie…");

  try {
    const created = await api("POST", "/events", payload);

    // Presigned POST: pola z odpowiedzi muszą być przed plikiem.
    const upload = new FormData();
    Object.entries(created.upload.fields).forEach(([k, v]) => upload.append(k, v));
    upload.append("file", photo);
    const up = await fetch(created.upload.url, { method: "POST", body: upload });

    form.reset();
    setStatus(statusNode, "");
    await refreshProfile().catch(() => {});
    if (up.ok) toast("Ogłoszenie przyjęte. Pojawi się w serwisie po przetworzeniu.");
    else toast(`Ogłoszenie zapisane, ale upload zdjęcia nie powiódł się (HTTP ${up.status}).`, "error");
    location.hash = "#ogloszenia";
  } catch (err) {
    setStatus(statusNode, "");
    handleError(err);
  } finally {
    button.disabled = false;
  }
});

$("logout").addEventListener("click", () => logout());
window.addEventListener("hashchange", render);

// --- start ---

function fillSelect(select, values) {
  select.replaceChildren(
    el("option", { value: "", textContent: "— wybierz —" }),
    ...values.map((v) => el("option", { value: v, textContent: v })),
  );
}
fillSelect($("category-select"), CONFIG.categories);
fillSelect($("district-select"), CONFIG.districts);

const savedKey = session.get();
if (savedKey) {
  login(savedKey).catch(() => logout());
} else {
  render();
}
