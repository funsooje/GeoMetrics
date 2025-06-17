# examples/example_submit_task.py

import argparse
import ee
from geometrics.gee_interface import initialize_gee, submitTask

def main():
    parser = argparse.ArgumentParser(
        description="Submit an export task for a test FeatureCollection using the LandsatNDVI package."
    )
    parser.add_argument(
        "--project",
        type=str,
        required=True,
        help="The GEE project ID."
    )
    args = parser.parse_args()

    initialize_gee(project=args.project)

    # Create a simple FeatureCollection with one point
    point = ee.Geometry.Point([-120.5, 46.8])
    feature = ee.Feature(point, {'test': 1})
    fc = ee.FeatureCollection([feature])

    # Submit export task
    submitTask(
        featureCollection=fc,
        saveFolder='TestExports', # will create the folder if it doesn't exist
        description='example_submit_task'
    )

    print("Export task submitted. Check the GEE Tasks tab or your Google Drive.")

if __name__ == "__main__":
    main()