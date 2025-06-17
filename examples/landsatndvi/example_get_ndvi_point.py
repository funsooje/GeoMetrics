# examples/example_get_ndvi_point.py

import argparse
from geometrics.gee_interface import initialize_gee
from geometrics.landsatndvi.ndvi import get_ndvi
import ee

def main():
    parser = argparse.ArgumentParser(
        description="Get NDVI value for a given point and date range using the LandsatNDVI package."
    )
    parser.add_argument(
        "--project",
        type=str,
        required=True,
        help="The GEE project ID."
    )
    parser.add_argument(
        "--lon",
        type=float,
        required=True,
        help="Longitude of the point."
    )
    parser.add_argument(
        "--lat",
        type=float,
        required=True,
        help="Latitude of the point."
    )
    parser.add_argument(
        "--start_date",
        type=str,
        required=True,
        help="Start date in format YYYY-MM-DD."
    )
    parser.add_argument(
        "--end_date",
        type=str,
        required=True,
        help="End date in format YYYY-MM-DD."
    )

    args = parser.parse_args()

    initialize_gee(project=args.project)

    point = ee.Geometry.Point([args.lon, args.lat])
    feature = ee.Feature(point, {
        'start_date': args.start_date,
        'end_date': args.end_date
    })

    result = get_ndvi(feature)

    print("NDVI Result:")
    print(result.getInfo())

if __name__ == "__main__":
    main()