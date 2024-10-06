from flask import Flask, request, jsonify  
from flask_cors import CORS
import ee
import geemap
import math
from google.oauth2 import service_account

app = Flask(__name__)
CORS(app)


SERVICE_ACCOUNT_FILE = './serviceaccount.json'


# Authenticate with the service account
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=['https://www.googleapis.com/auth/cloud-platform']
)


ee.Initialize(credentials)


def apply_scale_factors(image):
    optical_bands = image.select('SR_B.*').multiply(0.0000275).add(-0.2)
    thermal_band = image.select('ST_B10').multiply(0.00341802).add(149.0)
    return image.addBands(optical_bands, None, True).addBands(thermal_band, None, True)



# Ölçek faktörlerini uygulama fonksiyonu
def applyScaleFactors(image):
    opticalBands = image.select('SR_B.').multiply(0.0000275).add(-0.2)
    thermalBand = image.select('ST_B10').multiply(0.00341802).add(149.0)
    return image.addBands(opticalBands, None, True).addBands(thermalBand, None, True)



# Latitude ve longitude'a göre uydu görüntüsü alma
@app.route('/get_image', methods=['POST'])
def get_image():
    data = request.json
    latitude = data.get('latitude')
    longitude = data.get('longitude')

    if latitude is None or longitude is None:
        return jsonify({"error": "Latitude and longitude required"}), 400

    # Uydu görüntüsü için nokta oluştur
    point = ee.Geometry.Point([longitude, latitude])

    # LANDSAT verilerini al, bulut oranını ve tarih aralığını filtrele
    dataset = ee.ImageCollection("LANDSAT/LC09/C02/T1_L2") \
        .filterDate('2024-09-01', '2024-10-30') \
        .filterBounds(point) \
        .filterMetadata('CLOUD_COVER', 'less_than', 15)






    # Son alınan uydu verisini getir
    latest_image = dataset.sort('system:time_start', False).first()
    acquisition_time = latest_image.get('system:time_start').getInfo()
    
    
        # Metadata bilgilerini al
    info = latest_image.getInfo()
    properties = info.get('properties', {})

    # İstediğiniz bilgileri döndürmek için
    metadata = {
        "Landsat_Product_Identifier_L2": properties.get('LANDSAT_PRODUCT_ID', 'N/A'),
        "Landsat_Product_Identifier_L1": properties.get('LANDSAT_SCENE_ID', 'N/A'),
        "Landsat_Scene_Identifier": properties.get('LANDSAT_SCENE_ID', 'N/A'),
        "Date_Acquired": properties.get('DATE_ACQUIRED', 'N/A'),
        "Collection_Category": properties.get('COLLECTION_CATEGORY', 'N/A'),
        "Collection_Number": properties.get('COLLECTION_NUMBER', 'N/A'),
        "WRS_Path": properties.get('WRS_PATH', 'N/A'),
        "WRS_Row": properties.get('WRS_ROW', 'N/A'),
        "Nadir_Off_Nadir": properties.get('NADIR_OFF_NADIR', 'N/A'),
        "Roll_Angle": properties.get('ROLL_ANGLE', 'N/A'),
        "Date_Product_Generated_L2": properties.get('DATE_PRODUCT_GENERATED_L2', 'N/A'),
        "Date_Product_Generated_L1": properties.get('DATE_PRODUCT_GENERATED_L1', 'N/A'),
        "Start_Time": properties.get('SCENE_CENTER_TIME', 'N/A'), #!
        "Stop_Time": properties.get('SCENE_CENTER_TIME', 'N/A'),  #!
        "Station_Identifier": properties.get('STATION_ID', 'N/A'),
        "Day_Night_Indicator": properties.get('DAY_NIGHT_INDICATOR', 'N/A'), #!
        "Land_Cloud_Cover": properties.get('LAND_CLOUD_COVER', 'N/A'), #!
        "Scene_Cloud_Cover_L1": properties.get('CLOUD_COVER', 'N/A'),
        "Ground_Control_Points_Model": properties.get('GROUND_CONTROL_POINTS_MODEL', 'N/A'), 
        "Ground_Control_Points_Version": properties.get('GROUND_CONTROL_POINTS_VERSION', 'N/A'),
        "Geometric_RMSE_Model": properties.get('GEOMETRIC_RMSE_MODEL', 'N/A'),
        "Geometric_RMSE_Model_X": properties.get('GEOMETRIC_RMSE_MODEL_X', 'N/A'),
        "Geometric_RMSE_Model_Y": properties.get('GEOMETRIC_RMSE_MODEL_Y', 'N/A'),
        "Processing_Software_Version": properties.get('PROCESSING_SOFTWARE_VERSION', 'N/A'),
        "Sun_Elevation_L0RA": properties.get('SUN_ELEVATION', 'N/A'),
        "Sun_Azimuth_L0RA": properties.get('SUN_AZIMUTH', 'N/A'),
        "Data_Type_L2": properties.get('DATA_TYPE_L2', 'N/A'), #!
        "Sensor_Identifier": properties.get('SENSOR_ID', 'N/A'),
        "Satellite": properties.get('SPACECRAFT_ID', 'N/A')
    }

    

   
    # Tarih formatını çevirmek
    acquisition_time_human = ee.Date(acquisition_time).format('YYYY-MM-dd').getInfo()

    # Sonraki uydu geçişi hesaplama (Landsat'ın tekrar geçiş periyodu 16 gündür)
    next_acquisition_time = ee.Date(acquisition_time).advance(16, 'day').format('YYYY-MM-dd').getInfo()

    # Ölçek faktörlerini uygula ve ortalama birleştirilmiş görüntü oluştur
    rescale = dataset.map(applyScaleFactors)
    landsat9 = rescale.median()

    # Belirlenen alanı oluştur ve resmi kes
    lat_change = 90 / 111320
    lon_change = 90 / (111320 * math.cos(math.radians(latitude)))

    region = ee.Geometry.Rectangle([
        longitude - lon_change / 2,
        latitude - lat_change / 2,
        longitude + lon_change / 2,
        latitude + lat_change / 2
    ])

    # Görüntüyü bölgeye göre kırp
    clipped_image = landsat9.clip(region)
    
    # Görüntü URL'sini al
    map_id_dict = clipped_image.getMapId({
        'bands': ['SR_B4', 'SR_B3', 'SR_B2'],  # RGB bandları
        'min': 0,
        'max': 0.3
    })

    # Yanıt olarak döndürülecek sınırlar (bounds)
    bounds = {
        "north": latitude + lat_change / 2,
        "south": latitude - lat_change / 2,
        "east": longitude + lon_change / 2,
        "west": longitude - lon_change / 2
    }
    

    # JSON formatında tile_url ve ek verileri React'e döndür
    return jsonify({
        'tile_url': map_id_dict['tile_fetcher'].url_format,
        'latitude': latitude,
        'longitude': longitude,
        'bounds': bounds,
        'acquisition_time': acquisition_time_human,
        'next_acquisition_time': next_acquisition_time,
        'satellite': 'Landsat 9',
        'metadata': metadata
    })
    



@app.route('/get_image_url', methods=['POST'])
def get_png_url():
    data = request.json
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    
    # Define the point geometry
    point = ee.Geometry.Point([longitude, latitude])

    # Load the Landsat 9 dataset
    dataset = ee.ImageCollection("LANDSAT/LC09/C02/T1_L2") \
        .filterDate('2024-09-01', '2024-10-30') \
        .filterBounds(point) \
        .filterMetadata('CLOUD_COVER', 'less_than', 15)

    # Apply scale factors and calculate the median
    rescaled = dataset.map(apply_scale_factors)
    landsat9 = rescaled.median()

    # Visualization parameters (RGB)
    visualization = {
        'bands': ['SR_B4', 'SR_B3', 'SR_B2'],  # Red, Green, Blue bands
        'min': 0,  # Adjusted minimum value
        'max': 0.3  # Adjusted maximum value
    }

    # Get the MapId
    map_id_dict = landsat9.getMapId(visualization)

    # Calculate tile coordinates
    zoom_level = 12  # Adjust as needed
    x, y = lat_lon_to_tile(latitude, longitude, zoom_level)

    # Format the tile URL
    tile_url = map_id_dict['tile_fetcher'].url_format.format(z=zoom_level, x=x, y=y)

    return  tile_url


def lat_lon_to_tile(lat, lon, zoom):
    lat_rad = math.radians(lat)  # Convert latitude to radians
    n = 2.0 ** zoom  # Number of tiles at this zoom level

    # Calculate x and y tile coordinates
    x_tile = int((lon + 180.0) / 360.0 * n)  # x coordinate
    y_tile = int((1.0 - (math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi)) / 2.0 * n)  # y coordinate

    return x_tile, y_tile

if __name__ == '__main__':
    app.run(debug=True)
