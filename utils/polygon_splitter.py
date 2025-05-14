import pandas as pd
import numpy as np
import shapely.geometry
from shapely.geometry import Polygon
import ee
from multiprocess import Pool, cpu_count
from tqdm import tqdm
from hiergp import hierGP


grider = hierGP(base_size=25)

def create_poly_feature_collection(main_poly, poly_id, grid_level):
    feature_collection = []

    # Step 1: Get bounds of the main polygon
    minx, miny, maxx, maxy = main_poly.bounds
    data = {
        'longitude': [minx, minx, maxx, maxx],
        'latitude': [miny, maxy, miny, maxy]
    }

    # Step 2: Convert bounds to DataFrame and generate grids
    bounds_df = pd.DataFrame(data)
    grids = grider.generateGrids(bounds_df, grid_level)
    grids = grids[['l{}_x'.format(grid_level), 'l{}_y'.format(grid_level)]]
    grids.columns = ['x', 'y']

    # Step 3: Fill the grids
    filled_grids = pd.DataFrame([
        (x, y)
        for x in range(grids['x'].min(), grids['x'].max() + 1)
        for y in range(grids['y'].min(), grids['y'].max() + 1)
    ], columns=['x', 'y'])

    # Step 4: Generate polygons from the grid boxes
    polygons_df = grider.generateGridCoords(filled_grids, grid_level)

    # Step 5: Create feature collection
    for _, row in polygons_df.iterrows():
        grid_poly = Polygon(eval(row['poly']))
        clipped_poly = main_poly.intersection(grid_poly)
        was_clipped = not grid_poly.equals(clipped_poly)

        if not clipped_poly.is_empty:
            if isinstance(clipped_poly, (shapely.geometry.Polygon, shapely.geometry.MultiPolygon)):
                if isinstance(clipped_poly, shapely.geometry.Polygon):
                    polygons = [clipped_poly]
                else:
                    polygons = list(clipped_poly.geoms)

                for poly_instance in polygons:
                    ee_poly = ee.Geometry.Polygon(list(poly_instance.exterior.coords))
                    feature = ee.Feature(
                        ee_poly,
                        {
                            'poly_id': poly_id,
                            'grid': f"{row['x']}|{row['y']}",
                            'clipped': was_clipped
                        }
                    )
                    feature_collection.append(feature)

    return feature_collection


def create_feature_collection(geom, poly_id, grid_level=8):
    feature_collection = []

    if isinstance(geom, shapely.geometry.Polygon):
        geoms = [geom]
    else:
        geoms = geom.geoms

    for poly in geoms:
        poly_collection = create_poly_feature_collection(poly, poly_id, grid_level)
        feature_collection.extend(poly_collection)

    return feature_collection


def worker_function(args):
    row, id_column, grid_level = args
    poly_id = row[id_column]
    geom = row.geometry
    return create_feature_collection(geom, poly_id=poly_id, grid_level=grid_level)


def parallel_processing(poly_collection_db, id_column, grid_level=8):
    n_processes = cpu_count()
    args_list = [(row, id_column, grid_level) for _, row in poly_collection_db.iterrows()]

    with Pool(processes=n_processes) as pool:
        feature_collections = list(tqdm(pool.imap_unordered(worker_function, args_list), total=len(args_list)))

    feature_collection_list = [item for sublist in feature_collections for item in sublist]
    return feature_collection_list


def split_polygons_in_parallel(poly_collection_db, grid_level=8, id_column='ID'):
    """
    Splits polygons in a GeoDataFrame using a grid-based method and returns an Earth Engine FeatureCollection.

    Parameters:
        poly_collection_db (GeoDataFrame): A GeoDataFrame with polygon geometries.
        grid_level (int): The hierarchical grid level to use for splitting (default is 8).
        id_column (str): Name of the column containing unique polygon IDs (default is 'ID').

    Returns:
        ee.FeatureCollection: The resulting feature collection of split polygons.
    """
    features = parallel_processing(poly_collection_db, id_column=id_column, grid_level=grid_level)
    return features
