async function loadJobs() {
  const status = document.getElementById('status');
  const jobsContainer = document.getElementById('jobs');
  const searchInput = document.getElementById('search');
  const countrySelect = document.getElementById('country');
  const categorySelect = document.getElementById('category');

  try {
    const response = await fetch('../data/jobs.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    const jobs = Array.isArray(payload.jobs) ? payload.jobs : [];

    const countries = [...new Set(jobs.map(j => j.country).filter(Boolean))].sort();
    const categories = [...new Set(jobs.map(j => j.roleCategory).filter(Boolean))].sort();

    for (const country of countries) {
      const option = document.createElement('option');
      option.value = country;
      option.textContent = country;
      countrySelect.appendChild(option);
    }

    for (const category of categories) {
      const option = document.createElement('option');
      option.value = category;
      option.textContent = category;
      categorySelect.appendChild(option);
    }

    function render() {
      const query = searchInput.value.trim().toLowerCase();
      const country = countrySelect.value;
      const category = categorySelect.value;

      const filtered = jobs.filter(job => {
        const haystack = `${job.company || ''} ${job.title || ''}`.toLowerCase();
        return (!query || haystack.includes(query))
          && (!country || job.country === country)
          && (!category || job.roleCategory === category);
      });

      status.textContent = `${filtered.length} public jobs`;
      jobsContainer.innerHTML = '';

      if (filtered.length === 0) {
        jobsContainer.innerHTML = '<p>No jobs match the selected filters.</p>';
        return;
      }

      for (const job of filtered) {
        const article = document.createElement('article');
        article.className = 'job-card';
        article.innerHTML = `
          <h2>${job.title || 'Untitled role'}</h2>
          <p><strong>${job.company || 'Unknown company'}</strong></p>
          <p>${job.location || job.country || 'Location unavailable'}</p>
          <p>${job.roleCategory || ''}</p>
          <p><a href="${job.sourceUrl || job.scoutJobUrl || '#'}" target="_blank" rel="noopener">View role</a></p>
        `;
        jobsContainer.appendChild(article);
      }
    }

    searchInput.addEventListener('input', render);
    countrySelect.addEventListener('change', render);
    categorySelect.addEventListener('change', render);
    render();
  } catch (error) {
    status.textContent = 'Unable to load jobs.';
    console.error(error);
  }
}

loadJobs();
