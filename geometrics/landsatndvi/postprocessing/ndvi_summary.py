import pandas as pd
import glob
from os.path import join
from tqdm import tqdm

def combine_ndvi_csvs(basepath):
    """
    Combines multiple NDVI CSV result files from a local Drive-synced folder
    and computes summary metrics per polygon.

    Parameters:
        basepath (str): Path to the folder containing *_0.csv, *_1.csv files.

    Returns:
        pd.DataFrame: Final merged DataFrame with calculated NDVI statistics.
    """
    df = pd.DataFrame()
    all_files = glob.glob(join(basepath, "*.csv"))
    for i in tqdm(range(len(all_files))):
        idf = pd.read_csv(all_files[i])
        df = pd.concat([df, idf], ignore_index=True)

    # Filter valid rows
    df = df[df.landsat_count > 0]

    # Add computed columns
    df['i_mean'] = df.landsat_sum / df.landsat_count
    df['i_shift'] = df.i_mean / df.landsat_mean

    print("Calculated Average Mean Shift: {:.4f}".format(df.i_shift.mean()))
    print("Calculated Average Mean: {:.4f}".format(df.i_mean.mean()))
    print("Original Average Mean: {:.4f}".format(df.landsat_mean.mean()))

    poly_avg = df.landsat_sum.sum() / df.landsat_count.sum()
    print("Calculated Poly Average: {:.4f}".format(poly_avg))

    # Grouped summaries
    poly_average = df.groupby('poly_id').apply(
        lambda x: x['landsat_sum'].sum() / x['landsat_count'].sum()
    ).reset_index(name='Calc_Poly_Average')

    average_mean = df.groupby('poly_id')['i_mean'].mean().reset_index(name='I_Poly_Mean')
    average_mean_shift = df.groupby('poly_id')['i_shift'].mean().reset_index(name='I_Poly_Mean_Accuracy')
    original_average_mean = df.groupby('poly_id')['landsat_mean'].mean().reset_index(name='Average_Using_Just_Poly')

    # Final merged result
    result_df = pd.merge(poly_average, average_mean, on='poly_id')
    result_df = pd.merge(result_df, average_mean_shift, on='poly_id')
    result_df = pd.merge(result_df, original_average_mean, on='poly_id')

    return result_df
