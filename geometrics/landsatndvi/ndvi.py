import ee
from geometrics.utils.batch_submitter import submit_feature_batches


def qaMask(image, cloud_threshold=2, cloudshadow_threshold=2, snow_threshold=2):
    qa = image.select('QA_PIXEL')
    cloud = qa.bitwiseAnd(1 << 3).And(qa.bitwiseAnd(3 << 8).gte(cloud_threshold))
    cloudShadow = qa.bitwiseAnd(1 << 4).And(qa.bitwiseAnd(3 << 10).gte(cloudshadow_threshold))
    snow = qa.bitwiseAnd(1 << 5).And(qa.bitwiseAnd(3 << 12).gte(snow_threshold))
    mask = cloud.Or(cloudShadow).Or(snow).Not()
    return image.updateMask(mask)

def applyScaleFactors(image, scale_factors=None):
    if scale_factors is None:
        # Default scaling factors for SR_B4 and SR_B5.
        scale_factors = {'SR_B4': (0.0000275, -0.2), 'SR_B5': (0.0000275, -0.2)}
    for band, (mult, add) in scale_factors.items():
        scaled = image.select(band).multiply(mult).add(add)
        image = image.addBands(scaled.rename(band), overwrite=True)
    return image

def harmonization2OLI(image, slopes=None, offsets=None):
    if slopes is None:
        slopes = {'red': 0.9825, 'nir': 1.0073}
    if offsets is None:
        offsets = {'red': -0.0022, 'nir': -0.0021}
    red_band = image.select('SR_B3')  # Red for Landsat 5/7
    nir_band = image.select('SR_B4')  # NIR for Landsat 5/7
    red_adjusted = red_band.multiply(slopes['red']).add(offsets['red'])
    nir_adjusted = nir_band.multiply(slopes['nir']).add(offsets['nir'])
    image = image.addBands(red_adjusted.rename('SR_B4'), overwrite=True)
    image = image.addBands(nir_adjusted.rename('SR_B5'), overwrite=True)
    return image

def calculateNDVI(image):
    # Compute NDVI using the adjusted NIR and Red bands.
    ndvi = image.normalizedDifference(['SR_B5', 'SR_B4'])
    return image.select([]).addBands(ndvi.rename('NDVI'))

def getImageCollection(feature,
                       use_landsat5=True, use_landsat7=True,
                       use_landsat8=True, use_landsat9=True,
                       cloud_threshold=2, cloudshadow_threshold=2, snow_threshold=2,
                       scale_factors=None, slopes=None, offsets=None):
    """
    Retrieves a merged Landsat image collection based on the specified options.

    Parameters:
        feature (ee.Feature): contains point as aoi, start_date and end_date.
        use_landsat5 (bool): Include Landsat 5 collection (default True).
        use_landsat7 (bool): Include Landsat 7 collection (default True).
        use_landsat8 (bool): Include Landsat 8 collection (default True).
        use_landsat9 (bool): Include Landsat 9 collection (default True).
        cloud_threshold (int): Confidence threshold for clouds (default 2).
        cloudshadow_threshold (int): Confidence threshold for cloud shadows (default 2).
        snow_threshold (int): Confidence threshold for snow (default 2).
        scale_factors (dict): Optional dictionary for scaling factors. Example:
            {'SR_B4': (multiply, add), 'SR_B5': (multiply, add)}.
        slopes (dict): Optional dictionary for harmonization slopes. Example:
            {'red': value, 'nir': value}.
        offsets (dict): Optional dictionary for harmonization offsets. Example:
            {'red': value, 'nir': value}.

    Returns:
        ee.ImageCollection: Merged image collection (may be empty if no images match).
    """
    aoi = feature.geometry()  # Get the geometry for filtering.
    start = feature.get('start_date') # ee.Date(start_date)
    end = feature.get('end_date') # ee.Date(end_date)
    
    collections = []
    
    if use_landsat8:
        lc8 = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2') \
            .filterDate(start, end) \
            .filterBounds(aoi) \
            .map(lambda image: qaMask(image, cloud_threshold, cloudshadow_threshold, snow_threshold)) \
            .map(lambda image: applyScaleFactors(image, scale_factors)) \
            .map(calculateNDVI)
        collections.append(lc8)
    
    if use_landsat9:
        lc9 = ee.ImageCollection('LANDSAT/LC09/C02/T1_L2') \
            .filterDate(start, end) \
            .filterBounds(aoi) \
            .map(lambda image: qaMask(image, cloud_threshold, cloudshadow_threshold, snow_threshold)) \
            .map(lambda image: applyScaleFactors(image, scale_factors)) \
            .map(calculateNDVI)
        collections.append(lc9)
    
    if use_landsat7:
        le7 = ee.ImageCollection('LANDSAT/LE07/C02/T1_L2') \
            .filterDate(start, end) \
            .filterBounds(aoi) \
            .map(lambda image: qaMask(image, cloud_threshold, cloudshadow_threshold, snow_threshold)) \
            .map(lambda image: harmonization2OLI(image, slopes, offsets)) \
            .map(lambda image: applyScaleFactors(image, scale_factors)) \
            .map(calculateNDVI)
        collections.append(le7)
    
    if use_landsat5:
        lt5 = ee.ImageCollection('LANDSAT/LT05/C02/T1_L2') \
            .filterDate(start, end) \
            .filterBounds(aoi) \
            .map(lambda image: qaMask(image, cloud_threshold, cloudshadow_threshold, snow_threshold)) \
            .map(lambda image: harmonization2OLI(image, slopes, offsets)) \
            .map(lambda image: applyScaleFactors(image, scale_factors)) \
            .map(calculateNDVI)
        collections.append(lt5)
    
    if collections:
        mergedCollection = collections[0]
        for col in collections[1:]:
            mergedCollection = mergedCollection.merge(col)
    else:
        # Return an empty ImageCollection if no sensors are selected.
        mergedCollection = ee.ImageCollection([])
    
    return mergedCollection

def get_ndvi(feature):
    def process_image(img):
        geometry = feature.geometry()
        
        combined_reducer = ee.Reducer.mean().combine(
            reducer2=ee.Reducer.sum(),
            sharedInputs=True
        ).combine(
            reducer2=ee.Reducer.count(),
            sharedInputs=True
        )

        combined_results = img.reduceRegion(
            reducer=combined_reducer,
            geometry=geometry,
            scale=30,
            maxPixels=1e9,
            bestEffort=True
        )

        ndvimean_value = combined_results.get('NDVI_mean')
        ndvisum_value = combined_results.get('NDVI_sum')
        ndvicount_value = combined_results.get('NDVI_count')

        properties = ee.Dictionary.fromLists(
            ['landsat_mean', 'landsat_sum', 'landsat_count'],
            [ndvimean_value, ndvisum_value, ndvicount_value]
        )
        return feature.setMulti(properties)

    ndvi_collection = getImageCollection(feature=feature).mean()
    
    has_bands_condition = ndvi_collection.bandNames().length().eq(0)

    result_feature = ee.Feature(ee.Algorithms.If(
        has_bands_condition,
        feature,
        process_image(ndvi_collection)
    ))

    return ee.Feature(None, result_feature.toDictionary())
    
def submit_ndvi_batches(
    feature_list,
    year,
    count_per_batch=1000,
    task_name='ndvi_batch',
    start_at=0,
    stop_at=None,
    missing_numbers=None
):
    def enrich_feature(feature):
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"
        return get_ndvi(
            feature.set('year', year)
                   .set('start_date', start_date)
                   .set('end_date', end_date)
        )

    submit_feature_batches(
        feature_list=feature_list,
        enrich_function=enrich_feature,
        task_name=task_name,
        count_per_batch=count_per_batch,
        start_at=start_at,
        stop_at=stop_at,
        missing_numbers=missing_numbers
    )
