# convert_fgd_dem_to_geotiff

## Installation

### for macOS

```shell
% brew install gdal
% pipenv sync
```

## Usage

```shell
% pipenv run python -m comvert_fgd_dem
```

If it doesn't work, reinstall.

```shell
% brew install gdal
% pipenv install
% pipenv uninstall gdal
% pipenv install numpy
% pipenv run pip install GDAL==$(gdal-config --version) --global-option=build_ext --global-option="-I/usr/include/gdal"
% pipenv install gdal
```