# Notes

Notes regarding how to release anta package

## Package requirements

- `bumpver`
- `build`
- `twine`

## Bumping version

In a branch specific for this, use the `bumpver` tool.
It is configured to update:
* pyproject.toml
* docs/contribution.md
* docs/requirements-and-installation.md

For instance to bump a patch version:
```
bumpver update --patch
```

and for a minor version

```
bumpver update --minor
```

Tip: It is possible to check what the changes would be using `--dry`

```
bumpver update --minor --dry
```

## Creating release on Github

Create the release on Github with the appropriate tag `vx.x.x`

## Release version `x.x.x`

> [!IMPORTANT]
> TODO - make this a github workflow

`x.x.x` is the version to be released

This is to be executed at the top of the repo

1. Checkout the latest version of devel with the correct tag for the release
2. [Optional] Clean dist if required
3. Build the package locally
   ```
   python -m build
   ```
4. Check the package with `twine` (replace with your vesion)
    ```
    twine check dist/*
    ```
5. Upload the package to test.pypi
    ```
    twine upload -r testpypi dist/anta-x.x.x.*
    ```
6. Verify the package by installing it in a local venv and checking it installs
   and run correctly (run the tests)
   ```
   # In a brand new venv
   pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple --no-cache anta
   ```
7. Upload the package to pypi
    ```
    twine upload dist/anta-x.x.x.*
    ```
8. Like 5 but for normal pypi
   ```
   # In a brand new venv
   pip install anta
   ```
9. Test installed version
   ```
   anta --version
   ```