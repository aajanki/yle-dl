# Packaging

## pypi

Update yledl/version.py, ChangeLog

```sh
pytest-3 --geoblocked

git tag 20190331
git push
git push --tags

rm -rf dist build
python3 setup.py sdist bdist_wheel --universal
twine upload dist/*
```

Update gh-pages:
```sh
git checkout gh-pages
# edit index.html index-en.html
git push
git checkout master
```
