# Steps to create a new release

Write the new version number to yledl/version.py, update ChangeLog and commit.

```
pytest-3 --geoblocked

git push

git tag 20211203
git push --tags

rm -rf dist
python3 -m build
twine upload dist/*
```

Link the new release on the gh-pages:

```
git checkout gh-pages

# Edit index.html, index-en.html and index-sv.html

git commit -a
git push
git checkout master
```
