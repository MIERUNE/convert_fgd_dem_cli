import click

from . import ConvertDemToGeotiff


@click.command()
@click.option('--import_path', required=False, type=str, default="./DEM/FG-GML-6441-32-DEM5A.zip",
              help="変換対象のパスを指定（「xml」「.xmlが格納されたディレクトリ」「.xmlが格納された.zip」が対象です。） default=./DEM/")
@click.option('--output_path', required=False, type=str, default="./GeoTiff",
              help="GeoTiffを格納するディレクトリ default=./GeoTiff")
@click.option('--import_epsg', required=False, type=str, default="EPSG:4326",
              help="DEMのEPSGコード default=EPSG:4326")
@click.option('--output_epsg', required=False, type=str, default="EPSG:3857",
              help="GeoTiff（warp.tif）のEPSGコード default=EPSG:3857")
def main(import_path, output_path, import_epsg, output_epsg):
    cd = ConvertDemToGeotiff(
        import_path=import_path,
        output_path=output_path,
        import_epsg=import_epsg,
        output_epsg=output_epsg
    )
    cd.all_exe()


if __name__ == '__main__':
    main()