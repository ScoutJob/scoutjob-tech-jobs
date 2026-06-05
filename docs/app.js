"use strict";

const PAGE_SIZE = 100;

let allJobs = [];
let filteredJobs = [];
let visibleCount = PAGE_SIZE;

const elements = {
  generatedSummary: document.getElementById("generated-summary"),
  searchInput: document.getElementById("search-input"),
  companyFilter: document.getElementById("company-filter"),
  countryFilter: document.getElementById("country-filter"),
  categoryFilter: document.getElementById("category-filter"),
  remoteFilter: document.getElementById("remote-filter"),
  internshipFilter: document.getElementById("internship-filter"),
  clearFilters: document.getElementById("clear-filters"),
  resultCount: document.getElementById("result-count"),
  loadingState: document.getElementById("loading-state"),
  emptyState: document.getElementById("empty-state"),
  tableWrapper: document.getElementById("table-wrapper"),
  jobsBody: document.getElementById("jobs-body"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function normalizeText(value) {
  return String(value ?? "")
    .trim()
    .toLowerCase();
}

function formatDate(value) {
  if (!value) {
    return "—";
  }

  const parsed = new Date(value);

  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }

  return parsed.toLocaleDateString(
    "en-US",
    {
      year: "numeric",
      month: "short",
      day: "numeric",
    }
  );
}

function formatGeneratedAt(value) {
  if (!value) {
    return "Feed refresh time unavailable";
  }

  const parsed = new Date(value);

  if (Number.isNaN(parsed.getTime())) {
    return "Feed refresh time unavailable";
  }

  return `Feed refreshed ${parsed.toLocaleString("en-US")}`;
}

function effectiveJobDate(job) {
  return (
    job.datePostedUtc ||
    job.firstDiscoveredAtUtc ||
    ""
  );
}

function effectiveJobDateLabel(job) {
  return job.datePostedUtc
    ? "Posted"
    : "Found by ScoutJob";
}

function compareJobsNewestFirst(first, second) {
  const firstDate = new Date(
    effectiveJobDate(first)
  );

  const secondDate = new Date(
    effectiveJobDate(second)
  );

  const firstTime = Number.isNaN(firstDate.getTime())
    ? 0
    : firstDate.getTime();

  const secondTime = Number.isNaN(secondDate.getTime())
    ? 0
    : secondDate.getTime();

  return secondTime - firstTime;
}

function uniqueSortedValues(values) {
  return [
    ...new Set(
      values
        .map((value) => String(value ?? "").trim())
        .filter(Boolean)
    ),
  ].sort(
    (first, second) =>
      first.localeCompare(
        second,
        undefined,
        {
          sensitivity: "base",
        }
      )
  );
}

function replaceOptions(
  select,
  values,
  defaultLabel
) {
  const currentValue = select.value;

  select.innerHTML = "";

  const defaultOption = document.createElement("option");
  defaultOption.value = "";
  defaultOption.textContent = defaultLabel;

  select.appendChild(defaultOption);

  for (const value of values) {
    const option = document.createElement("option");

    option.value = value;
    option.textContent = value;

    select.appendChild(option);
  }

  select.value = values.includes(currentValue)
    ? currentValue
    : "";
}

function populateFilters() {
  replaceOptions(
    elements.companyFilter,
    uniqueSortedValues(
      allJobs.map((job) => job.company)
    ),
    "All companies"
  );

  replaceOptions(
    elements.countryFilter,
    uniqueSortedValues(
      allJobs.map((job) => job.country)
    ),
    "All countries"
  );

  replaceOptions(
    elements.categoryFilter,
    uniqueSortedValues(
      allJobs.map((job) => job.roleCategory)
    ),
    "All role categories"
  );
}

function currentFilters() {
  return {
    query: normalizeText(
      elements.searchInput.value
    ),

    company: elements.companyFilter.value,

    country: elements.countryFilter.value,

    category: elements.categoryFilter.value,

    remote: elements.remoteFilter.value,

    internship: elements.internshipFilter.value,
  };
}

function matchesSearch(job, query) {
  if (!query) {
    return true;
  }

  const searchable = [
    job.company,
    job.title,
    job.roleCategory,
    job.country,
    job.location,
  ]
    .map(normalizeText)
    .join(" ");

  return searchable.includes(query);
}

function jobMatchesFilters(job, filters) {
  if (
    filters.company &&
    job.company !== filters.company
  ) {
    return false;
  }

  if (
    filters.country &&
    job.country !== filters.country
  ) {
    return false;
  }

  if (
    filters.category &&
    job.roleCategory !== filters.category
  ) {
    return false;
  }

  if (
    filters.remote === "remote" &&
    job.isRemote !== true
  ) {
    return false;
  }

  if (
    filters.remote === "onsite" &&
    job.isRemote === true
  ) {
    return false;
  }

  if (
    filters.internship === "jobs" &&
    job.isInternship === true
  ) {
    return false;
  }

  if (
    filters.internship === "internships" &&
    job.isInternship !== true
  ) {
    return false;
  }

  return matchesSearch(
    job,
    filters.query
  );
}

function createLink({
  href,
  text,
  className,
}) {
  if (!href) {
    return "";
  }

  return `
    <a
      class="${className}"
      href="${escapeHtml(href)}"
      target="_blank"
      rel="noopener noreferrer"
    >
      ${escapeHtml(text)}
    </a>
  `;
}

function renderRows() {
  const jobsToDisplay = filteredJobs.slice(
    0,
    visibleCount
  );

  const rows = jobsToDisplay.map(
    (job) => {
      const displayedLocation =
        job.location ||
        job.country ||
        "Location unavailable";

      const dateLabel = effectiveJobDateLabel(job);

      const displayedDate = formatDate(
        effectiveJobDate(job)
      );

      const scoutJobLink = createLink({
        href: job.scoutJobUrl,
        text: "View on ScoutJob",
        className: "job-link scoutjob-link",
      });

      const sourceLink = createLink({
        href: job.sourceUrl,
        text: "Company source",
        className: "job-link source-link",
      });

      return `
        <tr>
          <td>
            <strong class="company-name">
              ${escapeHtml(job.company || "Unknown company")}
            </strong>
          </td>

          <td>
            <div class="job-title">
              ${escapeHtml(job.title || "Untitled role")}
            </div>

            ${
              job.isInternship
                ? `
                  <span class="badge">
                    Internship
                  </span>
                `
                : ""
            }

            ${
              job.isRemote
                ? `
                  <span class="badge">
                    Remote
                  </span>
                `
                : ""
            }
          </td>

          <td>
            ${escapeHtml(job.roleCategory || "—")}
          </td>

          <td>
            ${escapeHtml(displayedLocation)}
          </td>

          <td>
            <div class="date-cell">
              <span class="date-label">
                ${escapeHtml(dateLabel)}
              </span>

              <span>
                ${escapeHtml(displayedDate)}
              </span>
            </div>
          </td>

          <td>
            <div class="links-cell">
              ${scoutJobLink}
              ${sourceLink}
            </div>
          </td>
        </tr>
      `;
    }
  );

  if (
    filteredJobs.length > visibleCount
  ) {
    rows.push(`
      <tr>
        <td
          colspan="6"
          class="load-more-cell"
        >
          <button
            id="load-more"
            class="load-more-button"
            type="button"
          >
            Show more jobs
          </button>
        </td>
      </tr>
    `);
  }

  elements.jobsBody.innerHTML = rows.join("");

  const loadMoreButton = document.getElementById(
    "load-more"
  );

  if (loadMoreButton) {
    loadMoreButton.addEventListener(
      "click",
      () => {
        visibleCount += PAGE_SIZE;
        renderRows();
      }
    );
  }
}

function renderResults() {
  elements.loadingState.classList.add("hidden");

  if (filteredJobs.length === 0) {
    elements.tableWrapper.classList.add("hidden");
    elements.emptyState.classList.remove("hidden");
  } else {
    elements.emptyState.classList.add("hidden");
    elements.tableWrapper.classList.remove("hidden");
  }

  elements.resultCount.textContent =
    `${filteredJobs.length.toLocaleString("en-US")} delayed public jobs`;

  renderRows();
}

function applyFilters() {
  const filters = currentFilters();

  filteredJobs = allJobs
    .filter(
      (job) =>
        jobMatchesFilters(job, filters)
    )
    .sort(compareJobsNewestFirst);

  visibleCount = PAGE_SIZE;

  renderResults();
}

function clearFilters() {
  elements.searchInput.value = "";
  elements.companyFilter.value = "";
  elements.countryFilter.value = "";
  elements.categoryFilter.value = "";
  elements.remoteFilter.value = "";
  elements.internshipFilter.value = "";

  applyFilters();
}

function bindEvents() {
  elements.searchInput.addEventListener(
    "input",
    applyFilters
  );

  elements.companyFilter.addEventListener(
    "change",
    applyFilters
  );

  elements.countryFilter.addEventListener(
    "change",
    applyFilters
  );

  elements.categoryFilter.addEventListener(
    "change",
    applyFilters
  );

  elements.remoteFilter.addEventListener(
    "change",
    applyFilters
  );

  elements.internshipFilter.addEventListener(
    "change",
    applyFilters
  );

  elements.clearFilters.addEventListener(
    "click",
    clearFilters
  );
}

async function loadJobs() {
  elements.loadingState.classList.remove("hidden");
  elements.emptyState.classList.add("hidden");
  elements.tableWrapper.classList.add("hidden");

  try {
    const response = await fetch(
      "./data/jobs.json",
      {
        cache: "no-store",
      }
    );

    if (!response.ok) {
      throw new Error(
        `Feed request failed with HTTP ${response.status}`
      );
    }

    const payload = await response.json();

    const jobs = Array.isArray(payload)
      ? payload
      : Array.isArray(payload.jobs)
        ? payload.jobs
        : [];

    allJobs = jobs.sort(
      compareJobsNewestFirst
    );

    elements.generatedSummary.textContent =
      formatGeneratedAt(
        payload.generatedAtUtc
      );

    populateFilters();
    applyFilters();
  } catch (error) {
    console.error(
      "Unable to load ScoutJob public feed:",
      error
    );

    elements.loadingState.classList.add("hidden");
    elements.tableWrapper.classList.add("hidden");
    elements.emptyState.classList.remove("hidden");

    elements.resultCount.textContent =
      "Unable to load jobs";

    elements.emptyState.innerHTML = `
      <h3>
        The public feed could not be loaded
      </h3>

      <p>
        Please refresh the page in a few minutes. For faster access and better
        filtering, visit ScoutJob directly.
      </p>
    `;
  }
}

bindEvents();
loadJobs();
