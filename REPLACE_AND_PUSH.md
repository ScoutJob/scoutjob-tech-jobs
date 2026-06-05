# Replace and push

Copy the contents of this folder into the root of the existing `scoutjob-tech-jobs` repository, replacing matching files. Then run:

```bash
git add .
git commit -m "Fix delayed public job feed generation"
git push origin main
```

After pushing, open the repository on GitHub and run **Actions → Refresh public jobs → Run workflow** once. The hourly schedule remains enabled.
