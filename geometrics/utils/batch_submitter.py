import numpy as np
from tqdm import tqdm
from geometrics.gee_interface import submitTask
import ee

def submit_feature_batches(
    feature_list,
    enrich_function,
    count_per_batch=1000,
    task_name='feature_batch',
    start_at=0,
    stop_at=None,
    missing_numbers=None,
):
    """
    Submit processing tasks in batches from a list of ee.Feature.

    Parameters:
        feature_list (list): A list of ee.Feature objects.
        enrich_function (function): Function that takes a feature and returns enriched feature.
        count_per_batch (int): Number of features per batch.
        task_name (str): Prefix for the export task.
        start_at (int): Index to start batching from.
        stop_at (int or None): Last batch index to process (exclusive). Defaults to full range.
        missing_numbers (list): Specific batch indices to process (optional).
    """

    # Create batches
    total = len(feature_list)
    batches = int(np.ceil(total / count_per_batch))
    request_list = np.array_split(feature_list, batches)

    # Determine which batches to process
    if missing_numbers is None:
        if stop_at is None:
            stop_at = len(request_list)
        batch_range = range(start_at, stop_at)
    else:
        batch_range = [num for num in missing_numbers if num >= start_at]

    # Submit tasks
    for batchnum in tqdm(batch_range):
        feats = request_list[batchnum].tolist()
        ee_feats = ee.FeatureCollection(feats)
        ee_feats = ee_feats.map(enrich_function)
        submitTask(ee_feats, task_name, f"{task_name}_{batchnum}")