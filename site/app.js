const DATASETS_URL = "./datasets.json";
const VIEWER_HOST = "https://viewers.karospace.se";

const cardsEl = document.getElementById("cards");
const searchEl = document.getElementById("searchInput");
const emptyEl = document.getElementById("emptyState");
const resultCountEl = document.getElementById("resultCount");
const templateEl = document.getElementById("cardTemplate");

let allDatasets = [];

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

function createCard(dataset) {
  const clone = templateEl.content.cloneNode(true);
  const card = clone.querySelector(".card");
  const thumbEl = clone.querySelector(".card__thumb");
  const titleEl = clone.querySelector(".card__title");
  const slugEl = clone.querySelector(".card__slug");
  const descEl = clone.querySelector(".card__description");
  const citationEl = clone.querySelector(".card__citation");
  const typeEl = clone.querySelector(".badge--type");
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
  typeEl.textContent = dataset.type || "unknown";
  typeEl.dataset.type = dataset.type || "unknown";
  buttonEl.href = buildViewerUrl(dataset);

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
