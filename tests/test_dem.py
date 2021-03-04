import unittest
from pathlib import Path

from convert_fgd_dem import Dem


class DemTest(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_min_max_latlng(self):
        dem_ins = Dem(Path("../DEM/FG-GML-6441-32-DEM5A.zip"))
        min_max_latlng = {
            'lower_left_lat_min': 42.916666667,
            'lower_left_lon_min': 141.25,
            'upper_right_lat_max': 43.0,
            'upper_right_lon_max': 141.375
        }
        self.assertEqual(min_max_latlng, dem_ins.min_max_latlng)


if __name__ == "__main__":
    unittest.main()
