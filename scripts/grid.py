import numpy as np


latitude_min = -23.8663
latitude_max = -21.7820
longitude_min = -48.4917
longitude_max = -45.4194

distance_km = 10
spacing_latitude = distance_km / 111
mean_latitude = (latitude_min + latitude_max) / 2
spacing_longitude = distance_km / (111 * np.cos(np.radians(mean_latitude)))
latitudes = np.arange(latitude_min, latitude_max, spacing_latitude)
longitudes = np.arange(longitude_min, longitude_max, spacing_longitude)

points = [(lat, lon) for lat in latitudes for lon in longitudes]

import csv

with open('sao_paulo_grid_points.csv', mode='w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    writer.writerow(['latitude', 'longitude'])
    for point in points:
        writer.writerow(point)

print("Coordinates saved to sao_paulo_grid_points.csv")
