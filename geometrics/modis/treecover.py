import ee
from geometrics.utils.batch_submitter import submit_feature_batches
import pandas as pd
import glob
from os.path import join
from tqdm import tqdm

def get_treecover(feature):
    """
    Extract tree cover statistics from MOD44B for a given feature and year.
    Adds 'treecover_mean', 'treecover_sum', and 'treecover_count' to the feature.
    """
    year = feature.get('year')
    # MODIS MOD44B has yearly data starting from 2000
    dataset = ee.ImageCollection("MODIS/061/MOD44B") \
        .filter(ee.Filter.calendarRange(year, year, 'year')) \
        .select('Percent_Tree_Cover')

    image = dataset.first()
    if image is None:
        return feature.setMulti({
            'treecover_mean': -1,
            'treecover_count': -1
        })

    reducer = ee.Reducer.mean().combine(
        reducer2=ee.Reducer.count(),
        sharedInputs=True
    )

    stats = image.reduceRegion(
        reducer=reducer,
        geometry=feature.geometry(),
        scale=250,
        maxPixels=1e9
    )

    return feature.setMulti({
        'treecover_mean': stats.get('Percent_Tree_Cover_mean'),
        'treecover_count': stats.get('Percent_Tree_Cover_count')
    })

def submit_treecover_batches(
    feature_list,
    year,
    count_per_batch=1000,
    task_name='treecover_batch',
    start_at=0,
    stop_at=None,
    missing_numbers=None
):
    """
    Submit tree cover extraction tasks in batches from a list of ee.Feature.

    Parameters:
        feature_list (list): A list of ee.Feature objects.
        year (int): The year to assign to each feature for processing.
        count_per_batch (int): Number of features per batch.
        task_name (str): Prefix for the export task.
        start_at (int): Index to start batching from.
        stop_at (int or None): Last batch index to process (exclusive). Defaults to full range.
        missing_numbers (list or None): Specific batch indices to process (optional).
    """

    def enrich_feature(feature):
        return get_treecover(feature.set('year', year))

    submit_feature_batches(
        feature_list=feature_list,
        enrich_function=enrich_feature,
        count_per_batch=count_per_batch,
        task_name=task_name,
        start_at=start_at,
        stop_at=stop_at,
        missing_numbers=missing_numbers
    )


def combine_treecover_csvs(basepath):
    """
    Combine MODIS tree cover CSVs, filter valid records, and compute weighted statistics.

    Parameters:
        basepath (str): Directory containing tree cover CSV files.

    Returns:
        pd.DataFrame: Combined DataFrame with per-poly_id, per-year tree cover summaries.
    """
    df = pd.DataFrame()
    all_files = glob.glob(join(basepath, "*.csv"))

    for file in tqdm(all_files, desc="Reading CSV files"):
        try:
            idf = pd.read_csv(file)
            required = {'poly_id', 'treecover_mean', 'treecover_count', 'year'}
            if required.issubset(idf.columns):
                df = pd.concat([df, idf], ignore_index=True)
        except Exception as e:
            print(f"Error reading {file}: {e}")

    df = df[df.treecover_count > 0]

    # Calculate weighted mean
    df['weighted_contrib'] = df.treecover_mean * df.treecover_count
    weighted_sum = df.groupby(['poly_id', 'year'])['weighted_contrib'].sum()
    total_count = df.groupby(['poly_id', 'year'])['treecover_count'].sum()
    weighted_mean = (weighted_sum / total_count).reset_index(name='weighted_mean')

    # Calculate mean of means
    mean_of_means = df.groupby(['poly_id', 'year'])['treecover_mean'].mean().reset_index(name='mean_of_means')

    result_df = pd.merge(weighted_mean, mean_of_means, on=['poly_id', 'year'])
    return result_df