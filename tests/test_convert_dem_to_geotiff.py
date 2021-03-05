import unittest
from pathlib import Path

from osgeo import gdal, gdalconst

from convert_fgd_dem import ConvertDemToGeotiff


class ConvertDemToGeotiffTest(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_geotiff(self):
        cd = ConvertDemToGeotiff(
            import_path=Path("./target_files/FG-GML-6441-32-DEM5A.zip"),
            output_path=Path("./test_generated"),
        )
        cd.all_exe()
        geotiff_path = Path("./test_generated/dem_epsg4326.tif")
        src = gdal.Open(str(geotiff_path.resolve()), gdalconst.GA_ReadOnly)
        x_length = src.RasterXSize
        y_length = src.RasterYSize
        geo_transform = src.GetGeoTransform()
        self.assertEqual(2250, x_length)
        self.assertEqual(1500, y_length)
        self.assertEqual((141.25, 5.555555555555556e-05, 0.0, 43.0, 0.0, -5.555555533333253e-05), geo_transform)


if __name__ == "__main__":
    unittest.main()
