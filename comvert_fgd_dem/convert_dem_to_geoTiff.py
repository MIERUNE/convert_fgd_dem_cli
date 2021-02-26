import os
import xml.etree.ElementTree as et
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
    def __init__(self, import_path="./DEM/FG-GML-6441-32-DEM5A/", output_path="./GeoTiff"):
        self.import_path: Path = Path(import_path)
        self.output_path: Path = Path(output_path)
        self.xml_paths: list = [xml_path for xml_path in self.import_path.glob("*.xml")]
        self.dem_instances: list = [Dem(xml_path) for xml_path in self.xml_paths]

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

    # メタデータのリストを作成
    def get_metadata_list(self):
        """メタデータのリストを取得する

        Returns:
            list: メタデータのリスト

        """
        mesh_metadata_list = [dem.meta_data for dem in self.dem_instances]
        return mesh_metadata_list

    # ディレクトリ内のxmlから標高値を取得し標高値のnarrayを返す
    def _get_contents(self, dem_instance):
        contents_dict = {}

        meta_data = dem_instance.meta_data
        mesh_cord = meta_data["mesh_cord"]

        contents = dem_instance.contents
        elevations = [c[1] for c in contents]

        x_len = meta_data['grid_length']['x']
        y_len = meta_data['grid_length']['y']

        # 標高地を保存するための二次元配列を作成
        n_array = np.empty((y_len, x_len), np.float32)
        n_array.fill(-9999)

        start_point_x = meta_data['start_point']['x']
        start_point_y = meta_data['start_point']['y']

        # 標高を格納
        # データの並びは北西端から南東端に向かっているので行毎に座標を配列に入れていく
        index = 0
        for y in range(start_point_y, y_len):
            for x in range(start_point_x, x_len):
                insert_value = float(elevations[index])
                n_array[y][x] = insert_value
                index += 1
            start_point_x = 0

        contents_dict['mesh_cord'] = mesh_cord
        contents_dict['n_array'] = n_array

        return contents_dict

    # 標高値のリストを作成
    def get_contents_list(self):
        mesh_contents_list = [self._get_contents(dem) for dem in self.dem_instances]
        return mesh_contents_list

    # 複数のxmlを比較して左下と右上の緯度経度を見つける
    def find_lower_and_upper_latlon_from_all_xmls(self, meta_data_list):
        lower_left_lat_min = []
        lower_left_lon_min = []
        upper_right_lat_max = []
        upper_right_lon_max = []

        for meta_data in meta_data_list:
            lower_left_lat = meta_data['lower_corner']['lat']
            lower_left_lon = meta_data['lower_corner']['lon']
            upper_right_lat = meta_data['upper_corner']['lat']
            upper_right_lon = meta_data['upper_corner']['lon']

            lower_left_lat_min.append(lower_left_lat)
            lower_left_lon_min.append(lower_left_lon)
            upper_right_lat_max.append(upper_right_lat)
            upper_right_lon_max.append(upper_right_lon)

        return [min(lower_left_lat_min), min(lower_left_lon_min), max(upper_right_lat_max), max(upper_right_lon_max)]

    # 全xmlの座標を参照して画像の大きさを算出する
    def cal_gridcell_size_of_xml(self, pixel_size_x, pixel_size_y, lower_and_upper_latlon_list):
        lower_left_lat = lower_and_upper_latlon_list[0]
        lower_left_lon = lower_and_upper_latlon_list[1]
        upper_right_lat = lower_and_upper_latlon_list[2]
        upper_right_lon = lower_and_upper_latlon_list[3]

        xlen = round(abs((upper_right_lon - lower_left_lon) / pixel_size_x))
        ylen = round(abs((upper_right_lat - lower_left_lat) / pixel_size_y))

        return xlen, ylen

    # アレイと座標、ピクセルサイズ、グリッドサイズからGeoTiffを作成
    def write_geotiff(self, narray, lower_left_lon, upper_right_lat, pixel_size_x, pixel_size_y, xlen, ylen):
        # 「左上経度・東西解像度・回転（０で南北方向）・左上緯度・回転（０で南北方向）・南北解像度（北南方向であれば負）」
        geotransform = [lower_left_lon, pixel_size_x, 0, upper_right_lat, 0, pixel_size_y]

        merge_tiff_file = 'merge.tif'
        tiffFile = os.path.join(self.output_path, merge_tiff_file)

        # ドライバーの作成
        driver = gdal.GetDriverByName("GTiff")
        # ドライバーに対して「保存するファイルのパス・グリットセル数・バンド数・ラスターの種類・ドライバー固有のオプション」を指定してファイルを作成
        dst_ds = driver.Create(tiffFile, xlen, ylen, 1, gdal.GDT_Float32)
        # geotransformをセット
        dst_ds.SetGeoTransform(geotransform)

        # 作成したラスターの第一バンドを取得
        rband = dst_ds.GetRasterBand(1)
        # 第一バンドにアレイをセット
        rband.WriteArray(narray)
        # nodataの設定
        rband.SetNoDataValue(-9999)

        # EPSGコードを引数にとる前処理？
        ref = osr.SpatialReference()
        # EPSGコードを引数にとる
        ref.ImportFromEPSG(4326)
        # ラスターに投影法の情報を入れる
        dst_ds.SetProjection(ref.ExportToWkt())

        # ディスクへの書き出し
        dst_ds.FlushCache()

    # 再投影
    # 元画像のEPSGとwarp先のEPSGを引数にとる
    def resampling(self, srcSRS, outputSRS):
        warp_path = os.path.join(self.output_path, 'warp.tif')
        src_path = os.path.join(self.output_path, 'merge.tif')
        resampledRas = gdal.Warp(warp_path, src_path, srcSRS=srcSRS, dstSRS=outputSRS, resampleAlg="near")

        resampledRas.FlushCache()
        resampledRas = None

    # メタデータとコンテンツが与えられたらメッシュコードが同じなら結合
    def combine_data(self, meta_data_list, contents_list):
        mesh_data_list = []

        # 辞書のリストをメッシュコードをKeyにしてソート
        sort_metadata_list = sorted(meta_data_list, key=lambda x: x['mesh_cord'])
        sort_contents_list = sorted(contents_list, key=lambda x: x['mesh_cord'])
        # メタデータとコンテンツを結合
        for m, c in zip(sort_metadata_list, sort_contents_list):
            m.update(c)
            mesh_data_list.append(m)

        return mesh_data_list

    # 大きな配列を作って、そこに標高値をどんどん入れていく
    def find_coordinates_in_the_large_mesh(self, gridcell_size_list, lower_and_upper_latlon_list, metadata_list,
                                           contents_list):
        # 全xmlを包括するグリッドセル数
        large_mesh_xlen = gridcell_size_list[0]
        large_mesh_ylen = gridcell_size_list[1]

        # 全xmlを包括する配列を作成
        # グリッドセルサイズが10000以上なら処理を終了
        if large_mesh_xlen >= 10000 or large_mesh_ylen >= 10000:
            raise Exception('セルサイズが大きすぎます')

        large_mesh_narray = np.empty((large_mesh_ylen, large_mesh_xlen), np.float32)
        large_mesh_narray.fill(-9999)

        # マージ用配列の左下の座標を取得
        large_mesh_lower_left_lat = lower_and_upper_latlon_list[0]
        large_mesh_lower_left_lon = lower_and_upper_latlon_list[1]
        # マージ用配列の右上の座標を取得
        large_mesh_upper_right_lat = lower_and_upper_latlon_list[2]
        large_mesh_upper_right_lon = lower_and_upper_latlon_list[3]

        # マージ用配列のピクセルサイズ算出
        large_mesh_pixel_size_x = (large_mesh_upper_right_lon - large_mesh_lower_left_lon) / large_mesh_xlen
        large_mesh_pixel_size_y = (large_mesh_lower_left_lat - large_mesh_upper_right_lat) / large_mesh_ylen

        # メタデータと標高値を結合
        mesh_data_list = self.combine_data(metadata_list, contents_list)

        # メッシュのメッシュコードを取り出す
        for mesh_data in mesh_data_list:
            # データから標高値の配列を取得
            narray = mesh_data['narray']
            # グリッドセルサイズ
            xlen = mesh_data['grid_length']['x']
            ylen = mesh_data['grid_length']['y']
            # 読み込んだarrayの左下の座標を取得
            lower_left_lat = mesh_data['lower_corner']['lat']
            lower_left_lon = mesh_data['lower_corner']['lon']
            # (0, 0)からの距離を算出
            lat_distans = lower_left_lat - large_mesh_lower_left_lat
            lon_distans = lower_left_lon - large_mesh_lower_left_lon
            # numpy上の座標を取得(ピクセルサイズが少数のため誤差が出るから四捨五入)
            x_coordinate = round(lon_distans / large_mesh_pixel_size_x)
            y_coordinate = round(lat_distans / (-large_mesh_pixel_size_y))
            # スライスで指定する範囲を算出
            row_start = int(large_mesh_ylen - (y_coordinate + ylen))
            row_end = int(row_start + ylen)
            column_start = int(x_coordinate)
            column_end = int(column_start + xlen)
            # スライスで大きい配列に代入
            large_mesh_narray[row_start:row_end, column_start:column_end] = narray

        # アレイからGeoTiffを作成
        self.write_geotiff(large_mesh_narray, large_mesh_lower_left_lon,
                           large_mesh_upper_right_lat, large_mesh_pixel_size_x,
                           large_mesh_pixel_size_y, large_mesh_xlen, large_mesh_ylen)

        return large_mesh_narray

    # 処理を一括で行い、選択されたディレクトリに入っているxmlをGeoTiffにコンバートして指定したディレクトリに吐き出す
    # def all_exe(self, import_epsg, output_epsg):
    def all_exe(self):
        self.mesh_cords = self.get_mesh_cords()
        self.meta_data_list = self.get_metadata_list()
        self.contents_list = self.get_contents_list()
        # lower_and_upper_lat_lon_list = self.find_lower_and_upper_latlon_from_all_xmls(meta_data_list)
        #
        # pixel_size_x = meta_data_list[0]['pixel_size']['x']
        # pixel_size_y = meta_data_list[0]['pixel_size']['y']
        #
        # gridcell_size_list = self.cal_gridcell_size_of_xml(pixel_size_x,
        #                                                    pixel_size_y, lower_and_upper_lat_lon_list)
        #
        # large_mesh_contents_list = self.find_coordinates_in_the_large_mesh(
        #     gridcell_size_list,
        #     lower_and_upper_lat_lon_list,
        #     meta_data_list,
        #     contents
        # )
        #
        # # self.resampling('EPSG:4326', 'EPSG:2454')
        # self.resampling('EPSG:4326', output_epsg)
        #
        # merge_tiff_path = os.path.join(self.output_path, 'merge.tif')
        # warp_tiff_path = os.path.join(self.output_path, 'warp.tif')

        return
