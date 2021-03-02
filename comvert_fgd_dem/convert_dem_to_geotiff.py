import os
import xml.etree.ElementTree as et
import zipfile
from pathlib import Path

import numpy as np
from osgeo import gdal, osr


class Dem:
    def __init__(self, xml_path):
        self.xml_path: Path = xml_path
        self.raw_metadata: dict = {}
        self.contents: list = []
        self._read_dem()

        self.meta_data: dict = {}
        self.metadata_parser()

    def _read_dem(self):
        name_space = {
            'dataset': "http://fgd.gsi.go.jp/spec/2008/FGD_GMLSchema",
            'gml': 'http://www.opengis.net/gml/3.2',
        }

        tree = et.parse(self.xml_path)
        root = tree.getroot()

        raw_metadata = {}

        raw_metadata["mesh_code"] = int(root.find('dataset:DEM//dataset:mesh', name_space).text)
        raw_metadata["lower_corner"] = root.find(
            'dataset:DEM//dataset:coverage//gml:boundedBy//gml:Envelope//gml:lowerCorner',
            name_space).text
        raw_metadata["upper_corner"] = root.find(
            'dataset:DEM//dataset:coverage//gml:boundedBy//gml:Envelope//gml:upperCorner',
            name_space).text
        raw_metadata["grid_length"] = root.find('dataset:DEM//dataset:coverage//gml:gridDomain//gml:Grid//gml:high',
                                                name_space).text
        raw_metadata["start_point"] = root.find(
            'dataset:DEM//dataset:coverage//gml:coverageFunction//gml:GridFunction//gml:startPoint',
            name_space).text

        content = root.find('dataset:DEM//dataset:coverage//gml:rangeSet//gml:DataBlock//gml:tupleList',
                            name_space).text
        if content.startswith("\n"):
            strip_content = content.strip()
            content_list = [item.split(',') for item in strip_content.split("\n")]
            self.contents = content_list

        self.raw_metadata = raw_metadata

    def metadata_parser(self):
        lowers = self.raw_metadata["lower_corner"].split(" ")
        lower_corner = {
            "lat": float(lowers[0]),
            'lon': float(lowers[1])
        }

        uppers = self.raw_metadata["upper_corner"].split(" ")
        upper_corner = {
            "lat": float(uppers[0]),
            'lon': float(uppers[1])
        }

        grids = self.raw_metadata["grid_length"].split(" ")
        grid_length = {
            "x": int(grids[0]) + 1,
            'y': int(grids[1]) + 1
        }

        start_points = self.raw_metadata["start_point"].split(" ")
        start_point = {
            "x": int(start_points[0]),
            'y': int(start_points[1])
        }

        pixel_size = {
            'x': (upper_corner['lon'] - lower_corner['lon']) / grid_length['x'],
            'y': (lower_corner['lat'] - upper_corner['lat']) / grid_length['y']
        }

        meta_data = {
            'mesh_cord': self.raw_metadata["mesh_code"],
            "lower_corner": lower_corner,
            "upper_corner": upper_corner,
            "grid_length": grid_length,
            'start_point': start_point,
            "pixel_size": pixel_size,
        }

        self.meta_data = meta_data


class ConvertDemToGeotiff:
    def __init__(self,
                 import_path="./DEM/",
                 output_path="./GeoTiff",
                 import_epsg="EPSG:4326",
                 output_epsg="EPSG:4326"):
        self.import_path: Path = Path(import_path)
        self.output_path: Path = Path(output_path)
        self.import_epsg: str = import_epsg
        self.output_epsg: str = output_epsg
        self.xml_paths: list = self._get_xml_paths_from_import_path()
        self.dem_instances: list = [Dem(xml_path) for xml_path in self.xml_paths]
        self.mesh_cords: list = []
        self.meta_data_list: list = []
        self.content_list: list = []
        self.min_max_latlng: dict = {}
        self.pixel_size_x: float = 0.0
        self.pixel_size_y: float = 0.0
        self.merge_tiff_path: Path = None
        self.warp_tiff_path: Path = None

    def get_mesh_cords(self):
        """ファイルパスのリストからメッシュコードのリストを取得する

        Returns:
            list: メッシュコードのリスト

        Raises:
            - メッシュコードが6桁 or 8桁以外の場合はエラー
            - 2次メッシュと3次メッシュが混合している場合にエラー

        """
        third_mesh_cords = []
        second_mesh_cords = []

        for dem in self.dem_instances:
            mesh_cord = dem.meta_data["mesh_cord"]
            str_mesh = str(mesh_cord)
            if len(str_mesh) == 6:
                second_mesh_cords.append(mesh_cord)
            elif len(str_mesh) == 8:
                third_mesh_cords.append(mesh_cord)
            else:
                raise Exception(f"メッシュコードが不正です。mesh_code={mesh_cord}")

        # どちらもTrue、つまり要素が存在しているときにraise
        if all((third_mesh_cords, second_mesh_cords)):
            raise Exception('2次メッシュと3次メッシュが混合しています。')

        elif not third_mesh_cords:
            second_mesh_cords.sort()
            return second_mesh_cords
        else:
            third_mesh_cords.sort()
            return third_mesh_cords

    def get_metadata_list(self):
        """メタデータのリストを取得する

        Returns:
            list: メタデータのリスト

        """
        mesh_metadata_list = [dem.meta_data for dem in self.dem_instances]
        return mesh_metadata_list

    def _get_contents(self, dem_instance):
        """Demから標高値を取得し、メッシュコードと標高値（np.array）を格納した辞書を返す

        Args:
            dem_instance(Dem): Demクラスのインスタンス

        Returns:
            dict: メッシュコードと標高値（np.array）を格納した辞書

        """
        contents_dict = {
            "mesh_cord": None,
            "np_array": None
        }

        meta_data = dem_instance.meta_data
        mesh_cord = meta_data["mesh_cord"]

        contents = dem_instance.contents
        elevations = [c[1] for c in contents]

        x_len = meta_data['grid_length']['x']
        y_len = meta_data['grid_length']['y']

        # 標高地を保存するための二次元配列を作成
        np_array = np.empty((y_len, x_len), np.float32)
        np_array.fill(-9999)

        start_point_x = meta_data['start_point']['x']
        start_point_y = meta_data['start_point']['y']

        # 標高を格納
        # データの並びは北西端から南東端に向かっているので行毎に座標を配列に入れていく
        index = 0
        for y in range(start_point_y, y_len):
            for x in range(start_point_x, x_len):
                insert_value = float(elevations[index])
                np_array[y][x] = insert_value
                index += 1
            start_point_x = 0

        contents_dict['mesh_cord'] = mesh_cord
        contents_dict['np_array'] = np_array

        return contents_dict

    def get_contents_list(self):
        """Demからメッシュコードと標高値のnp.arrayを格納した辞書のリストを作成する

        Returns:
            list: メッシュコードと標高値のnp.arrayを格納した辞書のリスト

        """
        mesh_contents_list = [self._get_contents(dem) for dem in self.dem_instances]
        return mesh_contents_list

    def find_max_min_latlon_from_all_dems(self):
        """対象の全Demから緯度経度の最大・最小値を取得

        Returns:
            dict: 緯度経度の最大・最小値を格納した辞書

        """
        lower_left_lat_min = min([meta_data['lower_corner']['lat'] for meta_data in self.meta_data_list])
        lower_left_lon_min = min([meta_data['lower_corner']['lon'] for meta_data in self.meta_data_list])
        upper_right_lat_max = max([meta_data['upper_corner']['lat'] for meta_data in self.meta_data_list])
        upper_right_lon_max = max([meta_data['upper_corner']['lon'] for meta_data in self.meta_data_list])

        min_max_latlng = {
            "lower_left_lat_min": lower_left_lat_min,
            "lower_left_lon_min": lower_left_lon_min,
            "upper_right_lat_max": upper_right_lat_max,
            "upper_right_lon_max": upper_right_lon_max,
        }

        return min_max_latlng

    def calc_grid_cell_size(self, pixel_size_x, pixel_size_y, min_max_latlng):
        """対象の全Demの座標を取得し、出力画像の大きさを算出する

        Args:
            pixel_size_x: x方向のピクセルサイズ
            pixel_size_y: y方向のピクセルサイズ
            min_max_latlng: 緯度経度の最大・最小値が格納された辞書

        Returns:
            tuple: x/y方向の画像の大きさ

        """
        lower_left_lat = min_max_latlng["lower_left_lat_min"]
        lower_left_lon = min_max_latlng["lower_left_lon_min"]
        upper_right_lat = min_max_latlng["upper_right_lat_max"]
        upper_right_lon = min_max_latlng["upper_right_lon_max"]

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

    def resampling(self, src_epsg, output_epsg):
        """inとoutのepsgコードを受け取りdem_epsg4326.tifをresamplingした新たなGeoTiffを出力する

        Args:
            src_epsg:
            output_epsg:

        """
        warp_path = os.path.join(self.output_path, 'dem_warped.tif')
        src_path = os.path.join(self.output_path, 'dem_epsg4326.tif')
        resampledRas = gdal.Warp(warp_path, src_path, srcSRS=src_epsg, dstSRS=output_epsg, resampleAlg="near")

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
        sort_metadata_list = sorted(meta_data_list, key=lambda x: x['mesh_cord'])
        sort_contents_list = sorted(contents_list, key=lambda x: x['mesh_cord'])
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

    def _get_xml_paths_from_import_path(self):
        """指定したパスからxmlのPathオブジェクトのリストを作成

        """
        if self.import_path.is_dir():
            xml_paths = [xml_path for xml_path in self.import_path.glob("*.xml")]
            if xml_paths is None:
                raise Exception("指定ディレクトリに.xmlが存在しません")

        elif self.import_path.suffix == ".xml":
            xml_paths = [self.import_path]

        elif self.import_path.suffix == ".zip":
            with zipfile.ZipFile(self.import_path, 'r') as zip_data:
                zip_data.extractall(path=self.import_path.parent)
                extract_dir = self.import_path.parent / self.import_path.stem
                xml_paths = [xml_path for xml_path in extract_dir.glob("*.xml")]

        else:
            raise Exception("指定できる形式は「xml」「.xmlが格納されたディレクトリ」「.xmlが格納された.zip」のみです")

        return xml_paths

    def dem_to_terrain_rgb(self):
        pass

    def to_rgb_tiles(self):
        pass

    def to_mbtiles(self):
        pass

    def all_exe(self):
        """処理を一括で行い、選択されたディレクトリに入っているxmlをGeoTiffにコンバートして指定したディレクトリに吐き出す

        """
        self.mesh_cords = self.get_mesh_cords()
        self.meta_data_list = self.get_metadata_list()
        self.content_list = self.get_contents_list()
        self.min_max_latlng = self.find_max_min_latlon_from_all_dems()

        self.pixel_size_x = self.meta_data_list[0]['pixel_size']['x']
        self.pixel_size_y = self.meta_data_list[0]['pixel_size']['y']

        grid_cell_size = self.calc_grid_cell_size(self.pixel_size_x, self.pixel_size_y, self.min_max_latlng)

        large_mesh_contents_list = self.find_coordinates_in_large_mesh(
            grid_cell_size,
            list(self.min_max_latlng.values()),
            self.meta_data_list,
            self.content_list
        )

        self.resampling(self.import_epsg, self.output_epsg)

        self.merge_tiff_path = os.path.join(self.output_path, 'dem_epsg4326.tif')
        self.warp_tiff_path = os.path.join(self.output_path, 'dem_warped.tif')
