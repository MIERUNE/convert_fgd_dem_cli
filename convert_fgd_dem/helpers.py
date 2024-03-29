from osgeo import gdal


def warp(
        source_path=None,
        file_name="output.tif",
        output_path=None,
        epsg="EPSG:3857",
        no_data_value="None"):
    """
    EPSG:4326のTiffから新たなGeoTiffを出力する
    Args:
        source_path (Path or None):
        file_name (str):
        output_path (Path or None):
        epsg (str):
        no_data_value (int):
    """

    if not output_path.exists():
        output_path.mkdir()
    if source_path is None:
        source_path = output_path / file_name

    if file_name is None:
        file_name = "".join(f"dem_{epsg.lower()}.tif".split(":"))

    warp_path = str((output_path / file_name).resolve())
    src_path = str(source_path.resolve())

    resampled_ras = gdal.Warp(
        warp_path,
        src_path,
        srcSRS="EPSG:4326",
        dstSRS=epsg,
        dstNodata=no_data_value,
        resampleAlg="near"
    )
    resampled_ras.FlushCache()


def convert_height_to_R(height, no_data_value=-9999):
    if height == no_data_value:
        # nodataを標高値0として計算
        return 1
    r_min_height = 65536
    offset_height = int(height * 10) + 100000
    return offset_height // r_min_height


def convert_height_to_G(height, r_value, no_data_value=-9999):
    if height == no_data_value:
        # nodataを標高値0として計算
        return 134
    r_min_height = 65536
    g_min_height = 256
    offset_height = int(height * 10) + 100000
    return (offset_height - r_value * r_min_height) // g_min_height


def convert_height_to_B(height, r_value, g_value, no_data_value=-9999):
    if height == no_data_value:
        # nodataを標高値0として計算
        return 160
    r_min_height = 65536
    g_min_height = 256
    offset_height = int(height * 10) + 100000
    return offset_height - r_value * r_min_height - g_value * g_min_height
