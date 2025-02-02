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

`-l` - AccuWeather location key

`-k` - AccuWeather API key

`-i` - Weather update interval in seconds

`-m` - Display temperature in metric units (celsius)

By default, the weather does not update when the program is first run. This is because during testing, one might run the applet multiple times in a short period and we wouldn't want to exhaust our allotted AccuWeather requests.
The weather update interval is set to 60 minutes and the minimum that can be set with `-i` is 30. This is because AccuWeather limits the rate of requests to 50 per 24 hour period for most accounts.
To change this, you are free to modify the code.

# Example

The location and api key are acquired from AccuWeather. This starts the application on `WAYLAND_DISPLAY` socket `wayland-1` with an update interval of 45 minutes and temperature in celsius:

`WAYLAND_DISPLAY=wayland-1 python backdrop.py -l XXXXXXX -k XXXXXXX -i 45 -m`

# Screenshot

![backdrop](https://github.com/user-attachments/assets/4a2eee66-af39-4de5-ba5c-9f868341a001)

