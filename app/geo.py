from math import asin, cos, radians, sin, sqrt


def distance_km(latitude_a, longitude_a, latitude_b, longitude_b):
    """Return the great-circle distance between two coordinates in kilometers."""
    earth_radius_km = 6371.0088
    lat_delta = radians(latitude_b - latitude_a)
    lon_delta = radians(longitude_b - longitude_a)
    haversine = (
        sin(lat_delta / 2) ** 2
        + cos(radians(latitude_a))
        * cos(radians(latitude_b))
        * sin(lon_delta / 2) ** 2
    )
    return earth_radius_km * 2 * asin(sqrt(haversine))
