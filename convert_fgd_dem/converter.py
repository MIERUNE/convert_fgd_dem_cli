import os
import subprocess
from pathlib import Path

import numpy as np

from .dem import Dem
from .geotiff import Geotiff


class Converter:
    # リファクタリング後にやること
    # todo:terrain-rgbを吐き出すかどうかのオプションをつける
    # todo:投影変換するかどうかのオプションをつける
    # todo:吐き出すtiffは一つになるようにする
    # todo:import_epsgは必ず"EPSG:4326"だと思うので引数から外す
    def __init__(
        self,
        import_path="./DEM/FG-GML-6441-32-DEM5A.zip",
        output_path="./GeoTiff",
        import_epsg="EPSG:4326",
        output_epsg="EPSG:3857",
    ):
        self.import_path: Path = Path(import_path)
        self.output_path: Path = Path(output_path)
        self.import_epsg: str = import_epsg
        self.output_epsg: str = output_epsg

        self.dem = Dem(self.import_path)

    def _calc_image_size(self):
        """Dem境界の緯度経度とピクセルサイズから出力画像の大きさを算出する

        Returns:
            tuple: x/y方向の画像の大きさ

        """
        lower_left_lat = self.dem.bounds_latlng["lower_left"]["lat"]
        lower_left_lon = self.dem.bounds_latlng["lower_left"]["lon"]
        upper_right_lat = self.dem.bounds_latlng["upper_right"]["lat"]
        upper_right_lon = self.dem.bounds_latlng["upper_right"]["lon"]

        x_length = round(
            abs(
                (upper_right_lon - lower_left_lon)
                / self.dem.meta_data_list[0]["pixel_size"]["x"]
            )
        )
        y_length = round(
            abs(
                (upper_right_lat - lower_left_lat)
                / self.dem.meta_data_list[0]["pixel_size"]["y"]
            )
        )

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
        sort_metadata_list = sorted(meta_data_list, key=lambda x: x["mesh_code"])
        sort_contents_list = sorted(contents_list, key=lambda x: x["mesh_code"])
        # メタデータとコンテンツを結合
        for metadata, content in zip(sort_metadata_list, sort_contents_list):
            metadata.update(content)
            mesh_data_list.append(metadata)

        return mesh_data_list

    def create_data_for_geotiff(
        self, image_size, min_max_latlng, metadata_list, contents_list
    ):
        """対象のDemを全て取り込んだnp.arrayを作成する

        Args:
            image_size:
            min_max_latlng:
            metadata_list:
            contents_list:

        Returns:

        """
        # 全xmlを包括するグリッドセル数
        x_length = image_size[0]
        y_length = image_size[1]

        # グリッドセルサイズが10000以上なら処理を終了
        if x_length >= 10000 or y_length >= 10000:
            raise Exception(f"セルサイズが大きすぎます。x={x_length}・y={y_length}")

        # 全xmlを包括する配列を作成
        dem_array = np.empty((y_length, x_length), np.float32)
        dem_array.fill(-9999)

        corner_lat_lon = {
            "lower_left_lat": min_max_latlng[0],
            "lower_left_lon": min_max_latlng[1],
            "upper_right_lat": min_max_latlng[2],
            "upper_right_lon": min_max_latlng[3],
        }

        x_pixel_size = (
            corner_lat_lon["upper_right_lon"] - corner_lat_lon["lower_left_lon"]
        ) / x_length
        y_pixel_size = (
            corner_lat_lon["lower_left_lat"] - corner_lat_lon["upper_right_lat"]
        ) / y_length

        # メタデータと標高値を結合
        data_list = self._combine_meta_data_and_contents(metadata_list, contents_list)

        # メッシュのメッシュコードを取り出す
        for data in data_list:
            # データから標高値の配列を取得
            np_array = data["np_array"]
            # グリッドセルサイズ
            x_len = data["grid_length"]["x"]
            y_len = data["grid_length"]["y"]
            # 読み込んだarrayの左下の座標を取得
            lower_left_lat = data["lower_corner"]["lat"]
            lower_left_lon = data["lower_corner"]["lon"]
            # (0, 0)からの距離を算出
            lat_distance = lower_left_lat - corner_lat_lon["lower_left_lat"]
            lon_distance = lower_left_lon - corner_lat_lon["lower_left_lon"]
            # numpy上の座標を取得(ピクセルサイズが少数のため誤差が出るから四捨五入)
            x_coordinate = round(lon_distance / x_pixel_size)
            y_coordinate = round(lat_distance / (-y_pixel_size))
            # スライスで指定する範囲を算出
            row_start = int(y_length - (y_coordinate + y_len))
            row_end = int(row_start + y_len)
            column_start = int(x_coordinate)
            column_end = int(column_start + x_len)
            # スライスで大きい配列に代入
            dem_array[row_start:row_end, column_start:column_end] = np_array

        geo_transform = [
            corner_lat_lon["lower_left_lon"],
            x_pixel_size,
            0,
            corner_lat_lon["upper_right_lat"],
            0,
            y_pixel_size,
        ]

        data_for_geotiff = (
            geo_transform,
            dem_array,
            x_length,
            y_length,
            self.output_path,
        )
        return data_for_geotiff

    def dem_to_terrain_rgb(self):
        src_path = os.path.join(self.output_path, "dem_epsg4326.tif")

        filled_dem = "".join(
            f"dem_{self.output_epsg.lower()}_nodata_none.tif".split(":")
        )
        warp_path = os.path.join(self.output_path, filled_dem)

        warp_cmd = f"gdalwarp -overwrite -t_srs {self.output_epsg} -dstnodata None {src_path} {warp_path}"
        subprocess.check_output(warp_cmd, shell=True)

        rgb_name = "".join(f"dem_{self.output_epsg.lower()}_rgbify.tif".split(":"))
        rgb_path = os.path.join(self.output_path, rgb_name)

        rio_cmd = f"rio rgbify -b -10000 -i 0.1 {warp_path} {rgb_path}"

        subprocess.check_output(rio_cmd, shell=True)

    def all_exe(self):
        """処理を一括で行い、選択されたディレクトリに入っているxmlをGeoTiffにコンバートして指定したディレクトリに吐き出す"""
        bounds_values = [
            self.dem.bounds_latlng["lower_left"]["lat"],
            self.dem.bounds_latlng["lower_left"]["lon"],
            self.dem.bounds_latlng["upper_right"]["lat"],
            self.dem.bounds_latlng["upper_right"]["lon"],
        ]

        data_for_geotiff = self.create_data_for_geotiff(
            self._calc_image_size(),
            bounds_values,
            self.dem.meta_data_list,
            self.dem.np_array_list,
        )

        geotiff = Geotiff(*data_for_geotiff)
        geotiff.write_geotiff()
        geotiff.resampling()

        self.dem_to_terrain_rgb()
