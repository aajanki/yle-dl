# Steps to create a new release

Write the new version number to yledl/version.py, update ChangeLog and commit.

```
pytest-3 --geoblocked

git push

# Wait until the CircleCI checks are completed

# Pushing to releases/* tag runs the release pipeline on Github Actions
git tag releases/20211203
git push --tags
```

Link the new release on the gh-pages:

```
git checkout gh-pages

# Edit index.html, index-en.html and index-sv.html

PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -a
git push
git checkout master
```
