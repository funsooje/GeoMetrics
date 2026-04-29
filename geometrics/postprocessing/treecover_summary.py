import pandas as pd
import glob
from os.path import join
from tqdm import tqdm


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

    df['weighted_contrib'] = df.treecover_mean * df.treecover_count
    weighted_sum = df.groupby(['poly_id', 'year'])['weighted_contrib'].sum()
    total_count = df.groupby(['poly_id', 'year'])['treecover_count'].sum()
    weighted_mean = (weighted_sum / total_count).reset_index(name='weighted_mean')

    mean_of_means = df.groupby(['poly_id', 'year'])['treecover_mean'].mean().reset_index(name='mean_of_means')

    return pd.merge(weighted_mean, mean_of_means, on=['poly_id', 'year'])
