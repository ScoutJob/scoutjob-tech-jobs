function createOption(value, text) {
  const option = document.createElement('option');
  option.value = value;
  option.textContent = text;
  return option;
}

function safeHttpUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : '#';
  } catch {
    return '#';
  }
}

function appendText(parent, tag, text) {
  const element = document.createElement(tag);
  element.textContent = text;
  parent.appendChild(element);
  return element;
}

async function loadJobs() {
  const status = document.getElementById('status');
  const jobsContainer = document.getElementById('jobs');
  const searchInput = document.getElementById('search');
  const companySelect = document.getElementById('company');
  const countrySelect = document.getElementById('country');
  const categorySelect = document.getElementById('category');
  const remoteSelect = document.getElementById('remote');
  const internshipSelect = document.getElementById('internship');

  try {
    const response = await fetch('./data/jobs.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    const jobs = Array.isArray(payload.jobs) ? payload.jobs : [];

    const companies = [...new Set(jobs.map(j => j.company).filter(Boolean))].sort();
    const countries = [...new Set(jobs.map(j => j.country).filter(Boolean))].sort();
    const categories = [...new Set(jobs.map(j => j.roleCategory).filter(Boolean))].sort();

    for (const company of companies) companySelect.appendChild(createOption(company, company));
    for (const country of countries) countrySelect.appendChild(createOption(country, country));
    for (const category of categories) categorySelect.appendChild(createOption(category, category));

    function render() {
      const query = searchInput.value.trim().toLowerCase();
      const company = companySelect.value;
      const country = countrySelect.value;
      const category = categorySelect.value;
      const remote = remoteSelect.value;
      const internship = internshipSelect.value;

      const filtered = jobs.filter(job => {
        const haystack = `${job.company || ''} ${job.title || ''} ${job.location || ''}`.toLowerCase();
        return (!query || haystack.includes(query))
          && (!company || job.company === company)
          && (!country || job.country === country)
          && (!category || job.roleCategory === category)
          && (!remote || String(Boolean(job.isRemote)) === remote)
          && (!internship || String(Boolean(job.isInternship)) === internship);
      });

      status.textContent = `${filtered.length} delayed public jobs`;
      jobsContainer.replaceChildren();

      if (filtered.length === 0) {
        appendText(jobsContainer, 'p', 'No jobs match the selected filters.');
        return;
      }

      for (const job of filtered) {
        const article = document.createElement('article');
        article.className = 'job-card';
        appendText(article, 'h2', job.title || 'Untitled role');
        appendText(article, 'p', job.company || 'Unknown company').className = 'company';
        appendText(article, 'p', job.location || job.country || 'Location unavailable');
        appendText(article, 'p', job.roleCategory || 'Uncategorized');

        const linkParagraph = document.createElement('p');
        const link = document.createElement('a');
        link.href = safeHttpUrl(job.scoutJobUrl || job.sourceUrl || '#');
        link.target = '_blank';
        link.rel = 'noopener';
        link.textContent = 'View role';
        linkParagraph.appendChild(link);
        article.appendChild(linkParagraph);
        jobsContainer.appendChild(article);
      }
    }

    for (const element of [searchInput, companySelect, countrySelect, categorySelect, remoteSelect, internshipSelect]) {
      element.addEventListener(element === searchInput ? 'input' : 'change', render);
    }
    render();
  } catch (error) {
    status.textContent = 'Unable to load jobs.';
    console.error(error);
  }
}

loadJobs();
