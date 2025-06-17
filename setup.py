from setuptools import setup, find_packages

setup(
    name='GeoMetrics',
    version='0.0.1',
    packages=find_packages(),
    install_requires=[
        "earthengine-api",
    ],
    description='A Python package for extracting NDVI from Landsat imagery using Google Earth Engine',
    author='Funso Oje',
    license='MIT',
)