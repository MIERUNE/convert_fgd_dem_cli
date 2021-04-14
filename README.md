# convert_fgd_dem

## Overview

You can get the DEM data in xml format for any location from the following site.
[https://fgd.gsi.go.jp/download](https://fgd.gsi.go.jp/download)

Run the tool with downloaded "xml" or "directory containing .xml" or ".zip containing .xml" to generate GeoTiff and Terrain RGB (Tiff).

## Installation

### for macOS

```shell
% brew install gdal
% pipenv sync
```

## Usage

```shell
% pipenv run python -m convert_fgd_dem
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

## help

```shell
% pipenv run python -m convert_fgd_dem --help
Usage: __main__.py [OPTIONS]

Options:
  --import_path TEXT  変換対象のパスを指定（「xml」「.xmlが格納されたディレクトリ」「.xmlが格納された.zip」が対象です。） default=./DEM/FG-GML-6441-32-DEM5A.zip
  --output_path TEXT  GeoTiffを格納するディレクトリ default=./GeoTiff
  --import_epsg TEXT  DEMのEPSGコード default=EPSG:4326
  --output_epsg TEXT  GeoTiff（warp.tif）のEPSGコード default=EPSG:3857
  --help              Show this message and exit.
```

## sample

- Search of `644132` from `数値標高モデル` with [https://fgd.gsi.go.jp/download](https://fgd.gsi.go.jp/download) 
- Download `FG-GML-6441-32-DEM5A.zip`
- Make directory `DEM`
- Store `FG-GML-6441-32-DEM5A.zip` in `DEM`
- Run `pipenv run python -m convert_fgd_dem`