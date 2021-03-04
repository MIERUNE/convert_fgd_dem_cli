import os
import subprocess
from pathlib import Path

import numpy as np
from osgeo import gdal, osr

from .dem import Dem


class GeoTiff:
    def __init__(self):
        pass


class ConvertDemToGeotiff:
    def __init__(self,
                 import_path="./DEM/",
                 output_path="./GeoTiff",
                 import_epsg="EPSG:4326",
                 output_epsg="EPSG:3857"):
        self.import_path: Path = Path(import_path)
        self.output_path: Path = Path(output_path)
        self.import_epsg: str = import_epsg
        self.output_epsg: str = output_epsg
        self.mesh_codes: list = []
        self.meta_data_list: list = []
        self.np_array_list: list = []
        self.bounds_latlng: dict = {}
        self.pixel_size_x: float = 0.0
        self.pixel_size_y: float = 0.0
        self.merge_tiff_path: Path = None
        self.warp_tiff_path: Path = None
        self.dem = Dem(self.import_path)

    def calc_grid_cell_size(self, pixel_size_x, pixel_size_y, bounds_latlng):
        """対象の全Demの座標を取得し、出力画像の大きさを算出する

        Args:
            pixel_size_x: x方向のピクセルサイズ
            pixel_size_y: y方向のピクセルサイズ
            bounds_latlng: 緯度経度の最大・最小値が格納された辞書

        Returns:
            tuple: x/y方向の画像の大きさ

        """
        lower_left_lat = bounds_latlng["lower_left"]["lat"]
        lower_left_lon = bounds_latlng["lower_left"]["lon"]
        upper_right_lat = bounds_latlng["upper_right"]["lat"]
        upper_right_lon = bounds_latlng["upper_right"]["lon"]

        x_len = round(abs((upper_right_lon - lower_left_lon) / pixel_size_x))
        y_len = round(abs((upper_right_lat - lower_left_lat) / pixel_size_y))

        return x_len, y_len

    def write_geotiff(self, np_array, lower_left_lon, upper_right_lat, pixel_size_x, pixel_size_y, x_len, y_len):
        """標高と座標、ピクセルサイズ、グリッドサイズからGeoTiffを作成

        Args:
            np_array:
            lower_left_lon:
            upper_right_lat:
            pixel_size_x:
            pixel_size_y:
            x_len:
            y_len:

        """
        # 「左上経度・東西解像度・回転（０で南北方向）・左上緯度・回転（０で南北方向）・南北解像度（北南方向であれば負）」
        geo_transform = [lower_left_lon, pixel_size_x, 0, upper_right_lat, 0, pixel_size_y]

        merge_tiff_file = 'dem_epsg4326.tif'
        tiff_file = os.path.join(self.output_path, merge_tiff_file)

        # ドライバーの作成
        driver = gdal.GetDriverByName("GTiff")
        # ドライバーに対して「保存するファイルのパス・グリットセル数・バンド数・ラスターの種類・ドライバー固有のオプション」を指定してファイルを作成
        dst_ds = driver.Create(tiff_file, x_len, y_len, 1, gdal.GDT_Float32)
        # geo_transform
        dst_ds.SetGeoTransform(geo_transform)

        # 作成したラスターの第一バンドを取得
        r_band = dst_ds.GetRasterBand(1)
        # 第一バンドにアレイをセット
        r_band.WriteArray(np_array)
        # nodataの設定
        r_band.SetNoDataValue(-9999)

        # EPSGコードを引数にとる前処理？
        ref = osr.SpatialReference()
        # EPSGコードを引数にとる
        ref.ImportFromEPSG(4326)
        # ラスターに投影法の情報を入れる
        dst_ds.SetProjection(ref.ExportToWkt())

        # ディスクへの書き出し
        dst_ds.FlushCache()

    def resampling(self, src_epsg, output_epsg, nodata):
        """inとoutのepsgコードを受け取りdem_epsg4326.tifをresamplingした新たなGeoTiffを出力する

        Args:
            src_epsg:
            output_epsg:

        """
        file_name = "".join(f'dem_{self.output_epsg.lower()}.tif'.split(":"))
        warp_path = os.path.join(self.output_path, file_name)
        src_path = os.path.join(self.output_path, 'dem_epsg4326.tif')
        resampledRas = gdal.Warp(warp_path, src_path, srcSRS=src_epsg, dstSRS=output_epsg, dstNodata=nodata,
                                 resampleAlg="near")

        resampledRas.FlushCache()
        resampledRas = None

    def combine_meta_data_and_contents(self, meta_data_list, contents_list):
        """メッシュコードが同一のメタデータと標高値を結合する

        Args:
            meta_data_list:
            contents_list:

        Returns:

        """
        mesh_data_list = []

        # 辞書のリストをメッシュコードをKeyにしてソート
        sort_metadata_list = sorted(meta_data_list, key=lambda x: x['mesh_code'])
        sort_contents_list = sorted(contents_list, key=lambda x: x['mesh_code'])
        # メタデータとコンテンツを結合
        for metadata, content in zip(sort_metadata_list, sort_contents_list):
            metadata.update(content)
            mesh_data_list.append(metadata)

        return mesh_data_list

    def find_coordinates_in_large_mesh(self, grid_cell_size, min_max_latlng, metadata_list, contents_list):
        """対象のDemを全て取り込んだnp.arrayを作成する

        Args:
            grid_cell_size:
            min_max_latlng:
            metadata_list:
            contents_list:

        Returns:

        """
        # 全xmlを包括するグリッドセル数
        large_mesh_x_len = grid_cell_size[0]
        large_mesh_y_len = grid_cell_size[1]

        # 全xmlを包括する配列を作成
        # グリッドセルサイズが10000以上なら処理を終了
        if large_mesh_x_len >= 10000 or large_mesh_y_len >= 10000:
            raise Exception('セルサイズが大きすぎます')

        large_mesh_np_array = np.empty((large_mesh_y_len, large_mesh_x_len), np.float32)
        large_mesh_np_array.fill(-9999)

        # マージ用配列の左下の座標を取得
        large_mesh_lower_left_lat = min_max_latlng[0]
        large_mesh_lower_left_lon = min_max_latlng[1]
        # マージ用配列の右上の座標を取得
        large_mesh_upper_right_lat = min_max_latlng[2]
        large_mesh_upper_right_lon = min_max_latlng[3]

        # マージ用配列のピクセルサイズ算出
        large_mesh_pixel_size_x = (large_mesh_upper_right_lon - large_mesh_lower_left_lon) / large_mesh_x_len
        large_mesh_pixel_size_y = (large_mesh_lower_left_lat - large_mesh_upper_right_lat) / large_mesh_y_len

        # メタデータと標高値を結合
        mesh_data_list = self.combine_meta_data_and_contents(metadata_list, contents_list)

        # メッシュのメッシュコードを取り出す
        for mesh_data in mesh_data_list:
            # データから標高値の配列を取得
            np_array = mesh_data['np_array']
            # グリッドセルサイズ
            x_len = mesh_data['grid_length']['x']
            y_len = mesh_data['grid_length']['y']
            # 読み込んだarrayの左下の座標を取得
            lower_left_lat = mesh_data['lower_corner']['lat']
            lower_left_lon = mesh_data['lower_corner']['lon']
            # (0, 0)からの距離を算出
            lat_distance = lower_left_lat - large_mesh_lower_left_lat
            lon_distance = lower_left_lon - large_mesh_lower_left_lon
            # numpy上の座標を取得(ピクセルサイズが少数のため誤差が出るから四捨五入)
            x_coordinate = round(lon_distance / large_mesh_pixel_size_x)
            y_coordinate = round(lat_distance / (-large_mesh_pixel_size_y))
            # スライスで指定する範囲を算出
            row_start = int(large_mesh_y_len - (y_coordinate + y_len))
            row_end = int(row_start + y_len)
            column_start = int(x_coordinate)
            column_end = int(column_start + x_len)
            # スライスで大きい配列に代入
            large_mesh_np_array[row_start:row_end, column_start:column_end] = np_array

        # アレイからGeoTiffを作成
        self.write_geotiff(large_mesh_np_array, large_mesh_lower_left_lon,
                           large_mesh_upper_right_lat, large_mesh_pixel_size_x,
                           large_mesh_pixel_size_y, large_mesh_x_len, large_mesh_y_len)

        return large_mesh_np_array

    def dem_to_terrain_rgb(self):
        src_path = os.path.join(self.output_path, 'dem_epsg4326.tif')

        filled_dem = "".join(f'dem_{self.output_epsg.lower()}_nodata_none.tif'.split(":"))
        warp_path = os.path.join(self.output_path, filled_dem)

        warp_cmd = f"gdalwarp -overwrite -t_srs {self.output_epsg} -dstnodata None {src_path} {warp_path}"
        subprocess.check_output(warp_cmd, shell=True)

        rgb_name = "".join(f'dem_{self.output_epsg.lower()}_rgbify.tif'.split(":"))
        rgb_path = os.path.join(self.output_path, rgb_name)

        rio_cmd = f"rio rgbify -b -10000 -i 0.1 {warp_path} {rgb_path}"

        subprocess.check_output(rio_cmd, shell=True)

    def all_exe(self):
        """処理を一括で行い、選択されたディレクトリに入っているxmlをGeoTiffにコンバートして指定したディレクトリに吐き出す

        """
        self.mesh_codes = self.dem.mesh_code_list
        self.meta_data_list = self.dem.meta_data_list
        self.np_array_list = self.dem.np_array_list
        self.bounds_latlng = self.dem.bounds_latlng

        self.pixel_size_x = self.meta_data_list[0]['pixel_size']['x']
        self.pixel_size_y = self.meta_data_list[0]['pixel_size']['y']

        grid_cell_size = self.calc_grid_cell_size(self.pixel_size_x, self.pixel_size_y, self.bounds_latlng)

        lower_left_lat = self.bounds_latlng["lower_left"]["lat"]
        lower_left_lon = self.bounds_latlng["lower_left"]["lon"]
        upper_right_lat = self.bounds_latlng["upper_right"]["lat"]
        upper_right_lon = self.bounds_latlng["upper_right"]["lon"]
        bounds_values = [lower_left_lat, lower_left_lon, upper_right_lat, upper_right_lon]

        large_mesh_contents_list = self.find_coordinates_in_large_mesh(
            grid_cell_size,
            bounds_values,
            self.meta_data_list,
            self.np_array_list
        )

        self.resampling(self.import_epsg, self.output_epsg, nodata=-9999)

        self.merge_tiff_path = os.path.join(self.output_path, 'dem_epsg4326.tif')
        self.warp_tiff_path = os.path.join(self.output_path, "".join(f'dem_{self.output_epsg.lower()}.tif'.split(":")))

        self.dem_to_terrain_rgb()

# 選択された全てのxmlファイルからメッシュコードの一覧を取得し、メッシュコードごとのメタデータ・標高値を保持。
# 各xmlの最小・最大の緯度経度とグリッドの個数から1ピクセルで表現される距離（pixel_size）を割り出す
# 全メタデータの緯度経度から最小・最大の緯度経度を探しだす。
# 同時に各種類のDEMのピクセルサイズは全て同一であると仮定し、1xmlのpixel_sizeと最小・最大の緯度経度から全xmlのグリッド数を割り出す。
# 全xml分の大きさを持つ空のセルに各xmlの標高値を右上から格納していき、得られたセル・緯度経度・グリッドサイズなどの情報をもとにGeoTiffを作成。
# GeoTiffを指定のsridにwarpする
# GeoTiffをTerrain RGB形式に変換する
