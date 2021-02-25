import os
import re
from pathlib import Path

import numpy as np
from osgeo import gdal, osr


class ConvertDemToGeotiff:
    def __init__(self, import_path=Path("../DEM"), output_path=Path("../GeoTiff")):
        self.import_path = import_path
        self.output_path = output_path
        self.xml_paths = [xml_path for xml_path in self.import_path.glob("*.xml")]

    def get_mesh_cords(self):
        """ファイルパスのリストからメッシュコードのリストを取得する

        Returns:
            list: メッシュコードのリスト

        Raises:
            2次メッシュと3次メッシュが混合している場合にエラー

        """
        third_mesh_cords = []
        second_mesh_cords = []

        for xml_path in self.xml_paths:
            mesh_cord = self.get_metadata(xml_path)['mesh_cord']
            str_mesh = str(mesh_cord)
            if len(str_mesh) == 6:
                second_mesh_cords.append(mesh_cord)
            elif len(str_mesh) == 8:
                third_mesh_cords.append(mesh_cord)

        # どちらもTrue、つまり要素が存在しているときにraise
        if all(third_mesh_cords, second_mesh_cords):
            raise Exception('2次メッシュと3次メッシュが混合しています。')

        elif third_mesh_cords == []:
            second_mesh_cords.sort()
            return second_mesh_cords
        else:
            third_mesh_cords.sort()
            return third_mesh_cords

    @staticmethod
    def _get_mesh_code(xml_path):
        """xmlからメッシュコードを取得する

        Args:
            xml_path (Path): xmlのパス

        Returns:
            int: メッシュコード

        """
        with xml_path.open('r') as xml:
            # xmlの構文がおかしい？のでxml.etree.ElementTreeが利用できなさそう（要調査）
            pattern = re.compile('<mesh>(.+)</mesh>')
            for x_line in xml:
                match = pattern.search(x_line)
                if match is not None:
                    mesh_code = int(match.group(1))
                    break
        return mesh_code

    @staticmethod
    def _get_xml_content(xml_file, pattern_str):
        pattern = re.compile(pattern_str)
        for x_line in xml_file:
            match_obj = pattern.search(x_line)
            if match_obj is not None:
                return match_obj

    def get_metadata_from_xml(self, xml_path):
        """xmlからメタデータを取得し、メッシュコードやメタデータの辞書を返す

        Args:
            xml_path (Path): xmlのファイルパス

        Returns:
            object:

        """
        meta_data = {'mesh_cord': self._get_mesh_code(xml_path)}
        if meta_data["mesh_cord"] is None:
            raise Exception(f"{xml_path}からメッシュコードを取得できませんでした。")

        patterns = {
            "lower_corner": "<gml:lowerCorner>(.+) (.+)</gml:lowerCorner>",
            "upper_corner": "<gml:upperCorner>(.+) (.+)</gml:upperCorner>",
            "grid_length": "<gml:high>(.+) (.+)</gml:high>",
            "start_point": "<gml:startPoint>(.+) (.+)</gml:startPoint>"
        }

        with xml_path.open('r') as xml:
            for key, value in patterns.items():
                match_obj = self._get_xml_content(xml, value)
                if match_obj is None:
                    raise Exception(f"{value}がマッチしませんでした。")

                if key == "lower_corner":
                    lower_corner = {'lat': float(match_obj.group(1)), 'lon': float(match_obj.group(2))}
                    meta_data['lower_corner'] = lower_corner
                elif key == "upper_corner":
                    upper_corner = {'lat': float(match_obj.group(1)), 'lon': float(match_obj.group(2))}
                    meta_data['upper_corner'] = upper_corner
                elif key == "grid_length":
                    grid_length = {'x': int(match_obj.group(1)) + 1, 'y': int(match_obj.group(2)) + 1}
                    meta_data['grid_length'] = grid_length
                elif key == "start_point":
                    start_point = {'x': int(match_obj.group(1)), 'y': int(match_obj.group(2))}
                    meta_data['start_point'] = start_point

        upper_corner_lon = meta_data['upper_corner']['lon']
        lower_corner_lon = meta_data['lower_corner']['lon']
        xlen = meta_data['grid_length']['x']

        lower_corner_lat = meta_data['lower_corner']['lat']
        upper_corner_lat = meta_data['upper_corner']['lat']
        ylen = meta_data['grid_length']['y']

        # セルのサイズを算出
        # 右上から左下の緯度経度を引いてグリッドセルの配列数で割って1ピクセルのサイズを出す
        pixel_size = {
            'x': (upper_corner_lon - lower_corner_lon) / xlen,
            'y': (lower_corner_lat - upper_corner_lat) / ylen
        }

        meta_data['pixel_size'] = pixel_size

        return meta_data

    # メタデータのリストを作成
    def get_metadata_list(self, file_name_list):
        mesh_metadata_list = []

        for file_name in file_name_list:
            metadata = self.get_metadata(file_name)
            mesh_metadata_list.append(metadata)

        return mesh_metadata_list

    # ディレクトリ内のxmlから標高値を取得し標高値のnarrayを返す
    def get_contents(self, file_name):
        contents = {}
        xml_path = os.path.join(self.import_path, file_name)

        meta_data = self.get_metadata(file_name)

        with open(xml_path, "r") as x:
            # メッシュコードを取得
            for x_line in x:
                r = re.compile('<mesh>(.+)</mesh>')
                m = r.search(x_line)
                if m is not None:
                    mesh_cord = int(m.group(1))
                    break

            src_document = x.read()
            lines = src_document.split("\n")
            number_of_lines = len(lines)
            l1 = None
            l2 = None
            # 標高地のデータが出現するまでの行数を数える
            for n in range(number_of_lines):
                if lines[n].find("<gml:tupleList>") != -1:
                    l1 = n + 1
                    break
            # 標高地のデータが何行目で終わるか数える
            for n in range(number_of_lines - 1, -1, -1):
                if lines[n].find("</gml:tupleList>") != -1:
                    l2 = n - 1
                    break

        xlen = meta_data['grid_length']['x']
        ylen = meta_data['grid_length']['y']

        # 標高地を保存するための二次元配列を作成
        narray = np.empty((ylen, xlen), np.float32)
        # nodata(-9999)で初期化
        narray.fill(-9999)

        # 配列に入るデータ数を確認
        num_tuples = l2 - l1 + 1

        # スタートポジションを算出
        start_point_x = meta_data['start_point']['x']
        start_point_y = meta_data['start_point']['y']

        i = 0

        # 標高を格納
        # データの並びは北西端から南東端に向かっているので行毎に座標を配列に入れていく
        for y in range(start_point_y, ylen):
            for x in range(start_point_x, xlen):
                if i < num_tuples:
                    vals = lines[i + l1].split(",")
                    if len(vals) == 2:
                        narray[y][x] = float(vals[1])
                    i += 1
                else:
                    break

            if i == num_tuples:
                break
            # 次行の処理に移行する前にxtart_point_xは0で初期化
            start_point_x = 0

        contents['mesh_cord'] = mesh_cord
        contents['narray'] = narray

        return contents

    # 標高値のリストを作成
    def get_contents_list(self, file_name_list):
        mesh_contents_list = []

        for file_name in file_name_list:
            contents = self.get_contents(file_name)
            mesh_contents_list.append(contents)

        return mesh_contents_list

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

        return [min(lower_left_lat_min), min(lower_left_lon_min), \
                max(upper_right_lat_max), max(upper_right_lon_max)]

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
        geotransform = [lower_left_lon,
                        pixel_size_x,
                        0,
                        upper_right_lat,
                        0,
                        pixel_size_y]

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
        large_mesh_pixel_size_x = (large_mesh_upper_right_lon \
                                   - large_mesh_lower_left_lon) / large_mesh_xlen
        large_mesh_pixel_size_y = (large_mesh_lower_left_lat \
                                   - large_mesh_upper_right_lat) / large_mesh_ylen

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
    def all_exe(self, import_epsg, output_epsg):
        mesh_cords = self.get_mesh_cords()
        meta_data_list = self.get_metadata_list(self.xml_paths)
        contents = self.get_contents_list(self.xml_paths)
        lower_and_upper_lat_lon_list = self.find_lower_and_upper_latlon_from_all_xmls(meta_data_list)

        pixel_size_x = meta_data_list[0]['pixel_size']['x']
        pixel_size_y = meta_data_list[0]['pixel_size']['y']

        gridcell_size_list = self.cal_gridcell_size_of_xml(pixel_size_x,
                                                           pixel_size_y, lower_and_upper_lat_lon_list)

        large_mesh_contents_list = self.find_coordinates_in_the_large_mesh(
            gridcell_size_list,
            lower_and_upper_lat_lon_list,
            meta_data_list,
            contents
        )

        # self.resampling('EPSG:4326', 'EPSG:2454')
        self.resampling('EPSG:4326', output_epsg)

        merge_tiff_path = os.path.join(self.output_path, 'merge.tif')
        warp_tiff_path = os.path.join(self.output_path, 'warp.tif')

        return
