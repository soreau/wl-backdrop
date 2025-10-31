# Backdrop
### Time and weather applet for wayland

## Installation

Install pywayland:

`pip install pywayland`

Generate the protocols:

`python3 -m pywayland.scanner`

Download wl-backdrop:

`git clone https://github.com/soreau/wl-backdrop`

Run the application:

`python3 ./wl-backdrop/backdrop.py`

## Arguments

`-l` - OpenWeatherMap location

`-k` - OpenWeatherMap API key

`-i` - Weather update interval in seconds

`-m` - Display temperature in metric units (celsius)

# Example

The location and api key are acquired from OpenWeatherMap. This starts the application on `WAYLAND_DISPLAY` socket `wayland-1` with an update interval of 45 minutes and temperature in celsius:

`WAYLAND_DISPLAY=wayland-1 python backdrop.py -l "XXXXXXX" -k "XXXXXXX" -i 45 -m`

# Screenshot

![backdrop](https://github.com/user-attachments/assets/4a2eee66-af39-4de5-ba5c-9f868341a001)
