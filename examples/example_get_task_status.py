# examples/example_get_task_status.py

import argparse
from geometrics.gee_interface import initialize_gee, getTaskStatus

def main():
    parser = argparse.ArgumentParser(
        description="Test getTaskStatus function from the LandsatNDVI package."
    )
    parser.add_argument(
            "--project",
        type=str,
        required=True,
        help="The GEE project ID."
    )
    args = parser.parse_args()

    initialize_gee(project=args.project)

    status_df = getTaskStatus()
    print("Task Status DataFrame:")
    print(status_df)

if __name__ == "__main__":
    main()