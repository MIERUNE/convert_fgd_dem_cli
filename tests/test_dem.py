import unittest
from pathlib import Path

from convert_fgd_dem import Dem


class TestDem(unittest.TestCase):
    def test_bounds_latlng(self):
        dem_ins = Dem(Path("../DEM/FG-GML-6441-32-DEM5A.zip"))
        bounds_latlng = {
            "lower_left": {
                "lat": 42.916666667,
                "lon": 141.25
            },
            "upper_right": {
                "lat": 43.0,
                "lon": 141.375
            },
        }
        self.assertEqual(bounds_latlng, dem_ins.bounds_latlng)


if __name__ == "__main__":
    unittest.main()
