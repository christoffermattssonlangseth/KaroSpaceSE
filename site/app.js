const DATASETS_URL = "./datasets.json";
const VIEWER_HOST = "https://viewers.karospace.se";
const THEME_STORAGE_KEY = "karospace-theme";

const cardsEl = document.getElementById("cards");
const searchEl = document.getElementById("searchInput");
const emptyEl = document.getElementById("emptyState");
const resultCountEl = document.getElementById("resultCount");
const templateEl = document.getElementById("cardTemplate");
const themeToggleEl = document.getElementById("themeToggle");

let allDatasets = [];
const INTERACTIVE_SELECTOR = "a, button, input, select, textarea, label";

function readStoredTheme() {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "dark" || stored === "light") {
      return stored;
    }
  } catch (error) {
    // Ignore storage errors and fall back to defaults.
  }
  return null;
}

function detectSystemTheme() {
  if (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  ) {
    return "dark";
  }
  return "light";
}

function applyTheme(theme, options = {}) {
  const { persist = false } = options;
  const resolved = theme === "dark" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", resolved);

  if (themeToggleEl) {
    const isDark = resolved === "dark";
    themeToggleEl.textContent = isDark ? "Dark mode: on" : "Dark mode: off";
    themeToggleEl.setAttribute(
      "aria-label",
      isDark ? "Switch to light mode" : "Switch to dark mode"
    );
    themeToggleEl.setAttribute("aria-pressed", String(isDark));
  }

  if (persist) {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, resolved);
    } catch (error) {
      // Ignore storage errors in restrictive environments.
    }
  }
}

function initTheme() {
  const storedTheme = readStoredTheme();
  applyTheme(storedTheme || detectSystemTheme());

  if (!themeToggleEl) {
    return;
  }

  themeToggleEl.addEventListener("click", () => {
    const currentTheme = document.documentElement.getAttribute("data-theme");
    const nextTheme = currentTheme === "dark" ? "light" : "dark";
    applyTheme(nextTheme, { persist: true });
  });
}

function normalizePath(path) {
  return String(path || "").replace(/^\/+/, "");
}

function buildViewerUrl(dataset) {
  const path = normalizePath(dataset.r2_path);
  return `${VIEWER_HOST}/${path}`;
}

function buildSearchText(dataset) {
  const tags = Array.isArray(dataset.tags) ? dataset.tags.join(" ") : "";
  return [dataset.title, dataset.description, dataset.citation, tags]
    .join(" ")
    .toLowerCase();
}

function normalizeThumbnailPath(path) {
  const raw = String(path || "").trim();
  if (!raw) {
    return "";
  }
  if (
    raw.startsWith("http://") ||
    raw.startsWith("https://") ||
    raw.startsWith("data:") ||
    raw.startsWith("/")
  ) {
    return raw;
  }
  return `./${raw.replace(/^\.?\//, "")}`;
}

function openViewer(url) {
  if (!url) {
    return;
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

function createCard(dataset) {
  const clone = templateEl.content.cloneNode(true);
  const card = clone.querySelector(".card");
  const thumbEl = clone.querySelector(".card__thumb");
  const titleEl = clone.querySelector(".card__title");
  const slugEl = clone.querySelector(".card__slug");
  const descEl = clone.querySelector(".card__description");
  const citationEl = clone.querySelector(".card__citation");
  const tagsEl = clone.querySelector(".tag-list");
  const buttonEl = clone.querySelector(".button");

  const thumbnail = normalizeThumbnailPath(dataset.thumbnail);
  if (thumbnail) {
    thumbEl.src = thumbnail;
    thumbEl.alt = `${dataset.title || dataset.slug || "dataset"} preview`;
    thumbEl.classList.remove("hidden");
    card.classList.add("has-thumb");
    thumbEl.addEventListener("error", () => {
      thumbEl.classList.add("hidden");
      card.classList.remove("has-thumb");
    });
  }

  titleEl.textContent = dataset.title || dataset.slug;
  slugEl.textContent = dataset.slug ? `/${dataset.slug}` : "";
  descEl.textContent = dataset.description || "No description provided.";
  if (dataset.citation) {
    citationEl.textContent = dataset.citation;
    citationEl.classList.remove("hidden");
  }
  const viewerUrl = buildViewerUrl(dataset);
  buttonEl.href = viewerUrl;

  card.setAttribute("role", "link");
  card.setAttribute("tabindex", "0");
  card.setAttribute(
    "aria-label",
    `Open viewer for ${dataset.title || dataset.slug || "dataset"}`
  );

  card.addEventListener("click", (event) => {
    if (event.target instanceof Element && event.target.closest(INTERACTIVE_SELECTOR)) {
      return;
    }
    openViewer(viewerUrl);
  });

  card.addEventListener("keydown", (event) => {
    if (event.target instanceof Element && event.target.closest(INTERACTIVE_SELECTOR)) {
      return;
    }

    if (event.key !== "Enter" && event.key !== " ") {
      return;
    }

    event.preventDefault();
    openViewer(viewerUrl);
  });

  const tags = Array.isArray(dataset.tags) ? dataset.tags : [];
  tags.forEach((tag) => {
    const span = document.createElement("span");
    span.className = "tag";
    span.textContent = tag;
    tagsEl.appendChild(span);
  });

  card.dataset.searchText = buildSearchText(dataset);
  return clone;
}

function renderCards(datasets) {
  cardsEl.innerHTML = "";
  const fragment = document.createDocumentFragment();
  datasets.forEach((dataset) => fragment.appendChild(createCard(dataset)));
  cardsEl.appendChild(fragment);

  const count = datasets.length;
  resultCountEl.textContent = `${count} dataset${count === 1 ? "" : "s"} shown`;
  emptyEl.classList.toggle("hidden", count !== 0);
}

function filterDatasets() {
  const query = searchEl.value.trim().toLowerCase();
  if (!query) {
    renderCards(allDatasets);
    return;
  }

  const filtered = allDatasets.filter((dataset) => {
    return buildSearchText(dataset).includes(query);
  });
  renderCards(filtered);
}

async function loadDatasets() {
  const response = await fetch(DATASETS_URL, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load ${DATASETS_URL}: ${response.status}`);
  }
  const data = await response.json();
  if (!Array.isArray(data)) {
    throw new Error("datasets.json must contain an array.");
  }
  return data;
}

async function init() {
  initTheme();
  try {
    allDatasets = await loadDatasets();
    renderCards(allDatasets);
    searchEl.addEventListener("input", filterDatasets);
  } catch (error) {
    cardsEl.innerHTML = "";
    emptyEl.classList.remove("hidden");
    emptyEl.textContent = `Unable to load datasets: ${error.message}`;
    resultCountEl.textContent = "";
  }
}

init();
