import requests
from agents import function_tool
from rich.console import Console

console = Console()

@function_tool
def get_location():
    """Get the user's location based on IP.
    
    Returns:
        str: The user's location information or error message.
    """
    console.print("\nChecking location...", style="dim blue")
    url = "http://ip-api.com/json"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data['status'] == 'success':
            return data['city'], data['lat'], data['lon']
        else:
            return "Unknown location"
    except Exception as e:
        return f"Error fetching location: {str(e)}"

@function_tool
def get_weather(latitude: float, longitude: float):
    """Get current weather forecast using latitude and longitude.
    
    Args:
        latitude (float): The latitude of the location.
        longitude (float): The longitude of the location.
    
    Returns:
        str: The weather forecast details.
    """
    console.print(f"\nGetting weather for latitude {latitude}, longitude {longitude}", style="dim blue")
    headers = {'User-Agent': '(gpt-oss-tools, openai)'}
    points_url = f"https://api.weather.gov/points/{latitude},{longitude}"
    try:
        points_response = requests.get(points_url, headers=headers)
        points_response.raise_for_status()
        points_data = points_response.json()
        forecast_url = points_data['properties']['forecast']
        forecast_response = requests.get(forecast_url, headers=headers)
        forecast_response.raise_for_status()
        forecast_data = forecast_response.json()
        periods = forecast_data['properties']['periods']
        forecast_summary = "\n".join([f"{period['name']}: {period['detailedForecast']}" for period in periods])
        return f"Weather forecast:\n{forecast_summary}"
    except Exception as e:
        return f"Error fetching weather: {str(e)}"