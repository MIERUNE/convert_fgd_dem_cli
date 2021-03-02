# convert_fgd_dem_to_geotiff

## install

```shell
% pipenv install
% pipenv uninstall gdal
% pipenv install numpy
% pipenv run pip install GDAL==$(gdal-config --version) --global-option=build_ext --global-option="-I/usr/include/gdal"
% pipenv install gdal
```

## usage

```shell
% pipenv run python -m comvert_fgd_dem
```