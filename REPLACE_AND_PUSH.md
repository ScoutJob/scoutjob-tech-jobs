# GitHub Pages public feed publishing fix

The live GitHub Pages site publishes from `docs/`. The refresh workflow must therefore update both:

- `data/jobs.json` and `data/jobs.csv`
- `docs/data/jobs.json` and `docs/data/jobs.csv`

This version does that twice for safety:

1. `scripts/generate_feed.py` copies the generated feed into `docs/data/`.
2. `.github/workflows/refresh-jobs.yml` repeats the copy and verifies that the files match before committing.

## Replace the repository files and push

From your local `scoutjob-tech-jobs` repository folder, replace the files with the contents of this ZIP, then run:

```bash
git add .
git commit -m "Publish generated feed to GitHub Pages"
git pull --rebase origin main
git push origin main
```

## Run the workflow manually

Open GitHub → **Actions** → **Refresh public jobs** → **Run workflow**.

Wait for both workflows to finish successfully:

- `Refresh public jobs`
- `pages build and deployment`

Then verify:

```text
https://scoutjob.github.io/scoutjob-tech-jobs/data/jobs.json
https://scoutjob.github.io/scoutjob-tech-jobs/
```

The JSON URL should show a non-zero `total`, and the browser page should display jobs.
