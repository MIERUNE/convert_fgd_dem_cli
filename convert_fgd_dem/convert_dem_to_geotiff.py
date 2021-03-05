import os
import subprocess
from pathlib import Path

import numpy as np

from .dem import Dem
from .geotiff import Geotiff


class ConvertDemToGeotiff:
    def __init__(self,
                 import_path="./DEM/FG-GML-6441-32-DEM5A.zip",
                 output_path="./GeoTiff",
                 import_epsg="EPSG:4326",
                 output_epsg="EPSG:3857"):
        self.import_path: Path = Path(import_path)
        self.output_path: Path = Path(output_path)
        self.import_epsg: str = import_epsg
        self.output_epsg: str = output_epsg

        self.dem = Dem(self.import_path)
        self.mesh_codes: list = self.dem.mesh_code_list
        self.meta_data_list: list = self.dem.meta_data_list
        self.np_array_list: list = self.dem.np_array_list
        self.bounds_latlng: dict = self.dem.bounds_latlng

        self.pixel_size_x: float = self.meta_data_list[0]['pixel_size']['x']
        self.pixel_size_y: float = self.meta_data_list[0]['pixel_size']['y']

    def _calc_grid_cell_size(self):
        """Dem境界の緯度経度とピクセルサイズから出力画像の大きさを算出する

        Returns:
            tuple: x/y方向の画像の大きさ

        """
        lower_left_lat = self.bounds_latlng["lower_left"]["lat"]
        lower_left_lon = self.bounds_latlng["lower_left"]["lon"]
        upper_right_lat = self.bounds_latlng["upper_right"]["lat"]
        upper_right_lon = self.bounds_latlng["upper_right"]["lon"]

        x_length = round(abs((upper_right_lon - lower_left_lon) / self.pixel_size_x))
        y_length = round(abs((upper_right_lat - lower_left_lat) / self.pixel_size_y))

        return x_length, y_length

    @staticmethod
    def _combine_meta_data_and_contents(meta_data_list, contents_list):
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

    def create_data_for_geotiff(self, grid_cell_size, min_max_latlng, metadata_list, contents_list):
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
        mesh_data_list = self._combine_meta_data_and_contents(metadata_list, contents_list)

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

        geo_transform = [
            large_mesh_lower_left_lon,
            large_mesh_pixel_size_x,
            0,
            large_mesh_upper_right_lat,
            0,
            large_mesh_pixel_size_y
        ]

        data_for_geotiff = (geo_transform, large_mesh_np_array, large_mesh_x_len, large_mesh_y_len, self.output_path)
        return data_for_geotiff

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
        x_length, y_length = self._calc_grid_cell_size()

        bounds_values = [
            self.bounds_latlng["lower_left"]["lat"],
            self.bounds_latlng["lower_left"]["lon"],
            self.bounds_latlng["upper_right"]["lat"],
            self.bounds_latlng["upper_right"]["lon"]
        ]

        data_for_geotiff = self.create_data_for_geotiff(
            (x_length, y_length),
            bounds_values,
            self.meta_data_list,
            self.np_array_list
        )

        geotiff = Geotiff(*data_for_geotiff)
        geotiff.write_geotiff()
        geotiff.resampling()

        self.dem_to_terrain_rgb()
