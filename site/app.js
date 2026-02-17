const DATASETS_URL = "./datasets.json";
const VIEWER_HOST = "https://viewers.yourdomain.com";

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
  return [dataset.title, dataset.description, tags].join(" ").toLowerCase();
}

function createCard(dataset) {
  const clone = templateEl.content.cloneNode(true);
  const card = clone.querySelector(".card");
  const titleEl = clone.querySelector(".card__title");
  const descEl = clone.querySelector(".card__description");
  const typeEl = clone.querySelector(".badge--type");
  const tagsEl = clone.querySelector(".tag-list");
  const buttonEl = clone.querySelector(".button");

  titleEl.textContent = dataset.title || dataset.slug;
  descEl.textContent = dataset.description || "No description provided.";
  typeEl.textContent = dataset.type || "unknown";
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
