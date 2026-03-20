const DATASETS_URL = "./datasets.json";
const CONFIG_URL = "./config.json";
const DEFAULT_VIEWER_HOST = "https://viewers.karospace.se";
const THEME_STORAGE_KEY = "karospace-theme";

const cardsEl = document.getElementById("cards");
const searchEl = document.getElementById("searchInput");
const emptyEl = document.getElementById("emptyState");
const resultCountEl = document.getElementById("resultCount");
const templateEl = document.getElementById("cardTemplate");
const themeToggleEl = document.getElementById("themeToggle");

let allDatasets = [];
let viewerHost = DEFAULT_VIEWER_HOST;
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

function normalizeViewerHost(value) {
  const trimmed = String(value || "").trim().replace(/\/+$/, "");
  if (!trimmed) {
    return DEFAULT_VIEWER_HOST;
  }
  if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
    return trimmed;
  }
  return `https://${trimmed}`;
}

function buildViewerUrl(dataset) {
  const path = normalizePath(dataset.r2_path);
  return `${viewerHost}/${path}`;
}

function buildSearchText(dataset) {
  const tags = Array.isArray(dataset.tags) ? dataset.tags.join(" ") : "";
  return [dataset.title, dataset.description, dataset.citation, tags]
    .join(" ")
    .toLowerCase();
}

function isDevelopmentDataset(dataset) {
  return String(dataset.status || "").trim().toLowerCase() === "development";
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
  const link = document.createElement("a");
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

function createCard(dataset) {
  const clone = templateEl.content.cloneNode(true);
  const card = clone.querySelector(".card");
  const thumbWrapEl = clone.querySelector(".card__thumb-wrap");
  const thumbEl = clone.querySelector(".card__thumb");
  const thumbFallbackEl = clone.querySelector(".card__thumb-fallback");
  const titleEl = clone.querySelector(".card__title");
  const slugEl = clone.querySelector(".card__slug");
  const descEl = clone.querySelector(".card__description");
  const citationEl = clone.querySelector(".card__citation");
  const tagsEl = clone.querySelector(".tag-list");
  const buttonEl = clone.querySelector(".button");
  const previewLabel = String(dataset.preview_label || "").trim();
  const previewBackground = String(dataset.preview_background || "").trim().toLowerCase();

  if (previewLabel) {
    thumbFallbackEl.textContent = previewLabel;
    thumbFallbackEl.classList.add("card__thumb-fallback--label");
  }

  if (previewBackground === "light") {
    thumbWrapEl.classList.add("card__thumb-wrap--light");
  }

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
  titleEl.title = titleEl.textContent;
  slugEl.textContent = dataset.slug ? `/${dataset.slug}` : "";
  descEl.textContent = dataset.description || "No description provided.";
  descEl.title = descEl.textContent;
  if (dataset.citation) {
    citationEl.textContent = "";
    const labelEl = document.createElement("span");
    labelEl.className = "card__citation-label";
    labelEl.textContent = "Citation";
    const textEl = document.createElement("span");
    textEl.className = "card__citation-text";
    textEl.textContent = dataset.citation;
    citationEl.append(labelEl, textEl);
    citationEl.title = dataset.citation;
    citationEl.classList.remove("hidden");
  }
  const viewerUrl = buildViewerUrl(dataset);
  const actionLabel = String(dataset.action_label || "Open viewer").trim() || "Open viewer";
  buttonEl.href = viewerUrl;
  buttonEl.textContent = actionLabel;

  card.setAttribute("role", "link");
  card.setAttribute("tabindex", "0");
  card.setAttribute(
    "aria-label",
    `${actionLabel} for ${dataset.title || dataset.slug || "dataset"}`
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

function createCardsGrid(datasets) {
  const grid = document.createElement("div");
  grid.className = "cards-grid";
  datasets.forEach((dataset) => grid.appendChild(createCard(dataset)));
  return grid;
}

function createCardsSection(options) {
  const { eyebrow, title, description, datasets } = options;
  const section = document.createElement("section");
  section.className = "cards-section";

  if (title) {
    const header = document.createElement("div");
    header.className = "cards-section__head";

    if (eyebrow) {
      const eyebrowEl = document.createElement("p");
      eyebrowEl.className = "cards-section__eyebrow";
      eyebrowEl.textContent = eyebrow;
      header.appendChild(eyebrowEl);
    }

    const titleEl = document.createElement("h2");
    titleEl.className = "cards-section__title";
    titleEl.textContent = title;
    header.appendChild(titleEl);

    if (description) {
      const descriptionEl = document.createElement("p");
      descriptionEl.className = "cards-section__description";
      descriptionEl.textContent = description;
      header.appendChild(descriptionEl);
    }

    section.appendChild(header);
  }

  section.appendChild(createCardsGrid(datasets));
  return section;
}

function renderCards(datasets) {
  cardsEl.innerHTML = "";
  const developmentDatasets = [];
  const stableDatasets = [];

  datasets.forEach((dataset) => {
    if (isDevelopmentDataset(dataset)) {
      developmentDatasets.push(dataset);
      return;
    }
    stableDatasets.push(dataset);
  });

  if (stableDatasets.length) {
    if (developmentDatasets.length) {
      cardsEl.appendChild(
        createCardsSection({
          eyebrow: "Library",
          title: "Available tools and datasets",
          description: "Public KaroSpace viewers and tools available right now.",
          datasets: stableDatasets
        })
      );
    } else {
      cardsEl.appendChild(createCardsGrid(stableDatasets));
    }
  }

  if (developmentDatasets.length) {
    cardsEl.appendChild(
      createCardsSection({
        eyebrow: "In progress",
        title: "Under development",
        description:
          "Experimental viewers and tools currently being iterated on.",
        datasets: developmentDatasets
      })
    );
  }

  const count = datasets.length;
  resultCountEl.textContent = `${count} item${count === 1 ? "" : "s"} shown`;
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

async function loadSiteConfig() {
  try {
    const response = await fetch(CONFIG_URL, { cache: "no-store" });
    if (response.status === 404) {
      return { viewer_host: DEFAULT_VIEWER_HOST };
    }
    if (!response.ok) {
      throw new Error(`Failed to load ${CONFIG_URL}: ${response.status}`);
    }
    const data = await response.json();
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      throw new Error("config.json must contain an object.");
    }
    return data;
  } catch (error) {
    console.warn(`Falling back to default viewer host: ${error.message}`);
    return { viewer_host: DEFAULT_VIEWER_HOST };
  }
}

async function init() {
  initTheme();
  try {
    const config = await loadSiteConfig();
    viewerHost = normalizeViewerHost(config.viewer_host);
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
