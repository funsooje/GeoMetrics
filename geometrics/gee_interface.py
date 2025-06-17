import ee
import pandas as pd

def initialize_gee(project, opt_url="https://earthengine-highvolume.googleapis.com"):
    """
    Initializes the Google Earth Engine API with a specified project and opt_url.
    
    Parameters:
        project (str): The GEE project ID.
        opt_url (str): The Earth Engine URL to use for initialization.
        
    Raises:
        RuntimeError: If initialization fails.
    """
    try:
        ee.Initialize(opt_url=opt_url, project=project)
    except Exception as e:
        raise RuntimeError(
            "Google Earth Engine is not initialized. "
            "Please run 'earthengine authenticate' in your terminal."
        ) from e
    
def getTaskStatus():
    """
    Retrieves the status of tasks from Google Earth Engine,
    orders them by a custom state order (RUNNING, then PENDING, then others)
    and by submission time (earliest first).
    
    Returns:
        tasks_df (pd.DataFrame): DataFrame containing task details.
    """
    tasks = ee.data.listOperations()

    # return empty if no tasks are found
    if not tasks:
        print("No tasks found.")
        return pd.DataFrame(columns=['name', 'description', 'state', 'createTime'])

    tasks_list = []
    for task in tasks:
        metadata = task.get('metadata', {})
        if 'description' in metadata:
            description = metadata['description']
            state = metadata['state']
            # Attempt to retrieve a creation/submission time; assume 'createTime' exists.
            create_time = metadata.get('createTime', None)
            tasks_list.append({
                'name': task['name'],
                'description': description,
                'state': state,
                'createTime': create_time
            })
    
    tasks_df = pd.DataFrame(tasks_list)
    
    # Define custom ordering for state: RUNNING first, then PENDING, then all others.
    def state_sort_val(s):
        if s == "RUNNING":
            return 0
        elif s == "PENDING":
            return 1
        else:
            return 2

    tasks_df['state_sort'] = tasks_df['state'].apply(state_sort_val)
    
    # If createTime exists, convert to datetime for proper sorting.
    if tasks_df['createTime'].notnull().any():
        tasks_df['createTime'] = pd.to_datetime(tasks_df['createTime'], errors='coerce')
    
    # Sort by state (custom order) and then by createTime (ascending, so earliest first)
    tasks_df = tasks_df.sort_values(by=['state_sort', 'createTime'], ascending=[True, True])
    
    # Drop the temporary sort column.
    tasks_df = tasks_df.drop(columns=['state_sort'])

    # Format: "10:33:00 PM Mar 13"
    tasks_df['createTime'] = tasks_df['createTime'].dt.strftime("%I:%M:%S %p %b %d")
    
    print(tasks_df['state'].value_counts())
    return tasks_df


def submitTask(featureCollection, saveFolder, description):
    """
    Submits an Earth Engine task to export a FeatureCollection to Google Drive as a CSV file.

    Parameters:
        featureCollection (ee.FeatureCollection): The data to export.
        saveFolder (str): The name of the folder in Google Drive where the file will be saved.
        description (str): A description for the export task (used as the filename)
    """
    task_config = {
        'collection': featureCollection,
        'description': description,
        'fileFormat': 'CSV',
        'folder': saveFolder
    }
    task = ee.batch.Export.table.toDrive(**task_config)
    task.start()