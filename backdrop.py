#
# The MIT License (MIT)
#
# Copyright (c) 2025 Scott Moreau <oreaus@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#


from pywayland.client import Display
from pywayland.protocol.wayland import WlCompositor
from pywayland.protocol.wayland import WlShm
from pywayland.protocol.xdg_shell import XdgWmBase
from pywayland.utils import AnonymousFile
from datetime import datetime
import threading
import requests
import argparse
import signal
import select
import cairo
import json
import mmap
import time
import sys
import os

window_width = 1000
window_height = 200

def close(backdrop):
    backdrop["display"].disconnect()
    os.close(backdrop["weather_update_fd"])
    os.close(backdrop["time_update_fd"])
    os.close(backdrop["close_fd"])
    backdrop["running"] = False
    backdrop["thread"].join()
    exit(0)

def create_buffer(backdrop, width, height):
    anon_file = AnonymousFile(width * height * 4)
    anon_file.open()
    fd = anon_file.fd
    data = mmap.mmap(fileno=fd, length=width * height * 4, access=mmap.ACCESS_WRITE, offset=0)
    pool = backdrop["shm_binding"].create_pool(fd, width * height * 4)
    backdrop["buffer_id"] = 1
    if "buffer1" in backdrop:
        backdrop["buffer1"].destroy()
    backdrop["buffer1"] = pool.create_buffer(0, width, height, width * 4, WlShm.format.argb8888)
    pool.destroy()
    anon_file.close()

    backdrop["shm_data"] = data
    backdrop["cairo_surface"] = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)

def handle_xdg_surface_configure(xdg_surface, serial):
    backdrop = xdg_surface.user_data
    backdrop["wait_for_configure"] = False
    backdrop["xdg_surface"].ack_configure(serial)
    backdrop["surface"].commit()
    backdrop["display"].flush()

def handle_xdg_toplevel_configure(xdg_toplevel, width, height, flags):
    global window_width, window_height
    backdrop = xdg_toplevel.user_data
    if backdrop["wait_for_configure"]:
        return
    if width != 0 and height != 0 and window_width != width and window_height != height:
        window_width = width
        window_height = height
        create_buffer(backdrop, width, height)
        redraw(backdrop)

def handle_xdg_surface_close(xdg_toplevel):
    close(xdg_toplevel.user_data)

def handle_registry_global(wl_registry, id_num, iface_name, version):
    backdrop = wl_registry.user_data
    if iface_name == "wl_compositor":
        backdrop["compositor_enabled"] = True
        backdrop["compositor_binding"] = wl_registry.bind(id_num, WlCompositor, 1)
    elif iface_name == "xdg_wm_base":
        backdrop["xdg_enabled"] = True
        backdrop["xdg_binding"] = wl_registry.bind(id_num, XdgWmBase, 1)
    elif iface_name == "wl_shm":
        backdrop["shm_enabled"] = True
        backdrop["shm_binding"] = wl_registry.bind(id_num, WlShm, 1)
    return 1

def redraw(backdrop):
    current_time = datetime.now().time()
    formatted_time = current_time.strftime("%l:%M:%S")

    cr = cairo.Context(backdrop["cairo_surface"])
    center_x = window_width / 2
    center_y = window_height / 2
    radius = window_height / 3

    cr.set_operator(cairo.OPERATOR_CLEAR)
    
    cr.set_source_rgba(0, 0, 0, 0)
    cr.rectangle(0, 0, window_width, window_height)
    cr.fill()

    cr.set_operator(cairo.OPERATOR_SOURCE)

    # Draw semi-transparent background with gradient
    grad = cairo.LinearGradient(window_width / 2.0, 0, window_width / 2.0, window_height)
    grad.add_color_stop_rgba(0.0, 0.25, 0.25, 0.25, 0.0)
    grad.add_color_stop_rgba(1.0, 0.25, 0.25, 0.25, 0.75)
    cr.set_source(grad)
    cr.rectangle(0, 0, window_width, window_height)
    cr.fill()

    # Draw current time
    cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(window_width / 7)
    cr.set_source_rgba(1, 1, 1, 0.75)
    cr.move_to(window_width * 0.42, window_height * 0.75)
    cr.show_text(formatted_time)

    # Draw weather temperature
    cr.set_font_size(window_width / 10)
    (x, y, w, h, dx, dy) = cr.text_extents(backdrop["weather_temperature"])
    cr.move_to(window_width * 0.27 - w, window_height * 0.75)
    cr.show_text(backdrop["weather_temperature"])

    # Draw weather icon
    cr.set_operator(cairo.OPERATOR_OVER)
    cr.scale(2, 2)
    cr.set_source_surface(backdrop["weather_icon_surface"], window_width * 0.14, window_height * 0.17)
    cr.paint()

    # Upload buffer data to be read by the compositor
    backdrop["shm_data"].seek(0)
    backdrop["shm_data"].write(bytes(backdrop["cairo_surface"].get_data())) # BGRA
    backdrop["surface"].attach(backdrop["buffer1"], 0, 0)
    backdrop["surface"].damage(0, 0, window_width, window_height)
    backdrop["surface"].commit()
    backdrop["display"].flush()

def backdrop_create():
    backdrop = {}
    parser = argparse.ArgumentParser(
        prog="Backdrop",
        description="Display time and weather with icon.",
        epilog="Copyright (c) 2025 Scott Moreau <oreaus@gmail.com>")
    parser.add_argument("-l", "--location")
    parser.add_argument("-k", "--apikey")
    parser.add_argument("-i", "--interval")
    parser.add_argument("-m", "--metric", action="store_true")
    args = parser.parse_args()
    if args.apikey is None:
        print("Provide OpenWeatherMap APIKEY with -k or --apikey to enable weather updates.")
    if args.location is None:
        print("Provide OpenWeatherMap location with -l or --location to localize weather updates.")
    backdrop["weather_update_interval"] = "15"
    if args.interval is not None:
        if int(args.interval) < 1:
            print("Weather update interval must be greater or equal to 1 minute.")
            exit(-1)
        else:
            backdrop["weather_update_interval"] = args.interval
    if args.metric is True:
        print("Enabling metric mode (temperature units in celsius).")
    backdrop["weather_location_key"] = args.location
    backdrop["weather_api_key"] = args.apikey
    backdrop["weather_metric_units"] = args.metric

    backdrop["display"] = Display()
    backdrop["display"].connect()

    backdrop["registry"] = backdrop["display"].get_registry()
    backdrop["registry"].user_data = backdrop
    backdrop["registry"].dispatcher["global"] = handle_registry_global

    backdrop["compositor_enabled"] = False
    backdrop["xdg_enabled"] = False
    backdrop["shm_enabled"] = False
    backdrop["display"].roundtrip()

    if not backdrop["compositor_enabled"]:
        print("Protocol 'wl_compositor' not advertised by compositor. Cannot continue.", file=sys.stderr)
        backdrop["display"].disconnect()
        exit(-1)

    if not backdrop["xdg_enabled"]:
        print("Protocol 'xdg_shell' not advertised by compositor. Cannot continue.", file=sys.stderr)
        backdrop["display"].disconnect()
        exit(-1)

    if not backdrop["shm_enabled"]:
        print("Protocol 'wl_shm' not advertised by compositor. Cannot continue.", file=sys.stderr)
        backdrop["display"].disconnect()
        exit(-1)

    backdrop["surface"] = backdrop["compositor_binding"].create_surface()
    backdrop["xdg_surface"] = backdrop["xdg_binding"].get_xdg_surface(backdrop["surface"])
    backdrop["xdg_surface"].user_data = backdrop
    backdrop["xdg_surface"].dispatcher["configure"] = handle_xdg_surface_configure
    backdrop["xdg_toplevel"] = backdrop["xdg_surface"].get_toplevel()
    backdrop["xdg_toplevel"].user_data = backdrop
    backdrop["xdg_toplevel"].dispatcher["configure"] = handle_xdg_toplevel_configure
    backdrop["xdg_toplevel"].dispatcher["close"] = handle_xdg_surface_close
    backdrop["xdg_toplevel"].set_title("Backdrop")
    backdrop["xdg_toplevel"].set_app_id("backdrop")

    backdrop["surface"].commit()
    backdrop["display"].flush()
    create_buffer(backdrop, window_width, window_height)

    temperature_unit_symbol = "°F"
    if backdrop["weather_metric_units"] is True:
        temperature_unit_symbol = "°C"
    backdrop["weather_temperature"] = str(int(0.0)) + temperature_unit_symbol

    backdrop["weather_icon_directory"] = "weather-icons"
    os.makedirs(backdrop["weather_icon_directory"], exist_ok=True)

    weather_icon_name = "10n.png"
    weather_icon_path = backdrop["weather_icon_directory"] + "/" + weather_icon_name

    if not os.path.exists(weather_icon_path):
        weather_icon_url = "https://openweathermap.org/img/wn/" + weather_icon_name
        img_data = requests.get(weather_icon_url).content
        with open(weather_icon_path, 'wb') as weather_icon:
            weather_icon.write(img_data)

    backdrop["weather_icon_surface"] = cairo.ImageSurface.create_from_png(weather_icon_path)

    backdrop["surface"].commit()
    backdrop["display"].flush()

    backdrop["wait_for_configure"] = True
    while backdrop["wait_for_configure"]:
        backdrop["display"].roundtrip()

    return backdrop

backdrop = backdrop_create()

def signal_handler(sig, frame):
    os.write(backdrop["close_fd"], b"00000000")

def update_time_info():
    redraw(backdrop)

def update_weather_info():
    if backdrop["weather_api_key"] is None:
        print("Set OpenWeatherMap api key to enable weather updates.")
        return
    if backdrop["weather_location_key"] is None:
        print("Set OpenWeatherMap location to get localized weather updates.")
        backdrop["weather_location_key"] = "Colorado%20Springs"

    current_time = datetime.now().time()
    formatted_time = current_time.strftime("%l:%M:%S")
    print(formatted_time, "- Updating weather information..")

    try:
        if backdrop["weather_metric_units"] is True:
            units = "metric"
        else:
            units = "imperial"
        weather_data_url = "http://api.openweathermap.org/data/2.5/weather?q=" + str(backdrop["weather_location_key"]) + "&units=" + units + "&appid=" + str(backdrop["weather_api_key"])
        weather_data = json.loads(requests.get(weather_data_url).content)
        if backdrop["weather_metric_units"] is True:
            backdrop["weather_temperature"] = str(int(weather_data["main"]["temp"])) + "°C"
        else:
            backdrop["weather_temperature"] = str(int(weather_data["main"]["temp"])) + "°F"
        weather_icon_code = weather_data["weather"]["icon"]
        weather_icon_name = weather_icon_code + ".png"
        weather_icon_path = backdrop["weather_icon_directory"] + "/" + weather_icon_name
        if not os.path.exists(weather_icon_path):
            weather_icon_url = "https://openweathermap.org/img/wn/" + weather_icon_name
            img_data = requests.get(weather_icon_url).content
            with open(weather_icon_path, 'wb') as weather_icon:
                weather_icon.write(img_data)
        backdrop["weather_icon_surface"] = cairo.ImageSurface.create_from_png(weather_icon_path)
        print("Weather information updated successfully:", backdrop["weather_temperature"])
    except Exception as e:
        print("Failed to update weather:", e)
        #print(weather_data)
        pass

def timer_thread():
    i = 0
    timeout = int(backdrop["weather_update_interval"])
    while backdrop["running"]:
        os.write(backdrop["time_update_fd"], b"00000000")
        time.sleep(1)
        i = i + 1
        if i >= 60 * timeout:
            os.write(backdrop["weather_update_fd"], b"00000000")
            i = 0

def main():
    signal.signal(signal.SIGINT, signal_handler)
    display_fd = backdrop["display"].get_fd()
    epoll = select.epoll()
    backdrop["weather_update_fd"] = os.eventfd(0, os.EFD_CLOEXEC)
    backdrop["time_update_fd"] = os.eventfd(0, os.EFD_CLOEXEC)
    backdrop["close_fd"] = os.eventfd(0, os.EFD_CLOEXEC)
    epoll.register(display_fd, select.EPOLLIN)
    epoll.register(backdrop["weather_update_fd"], select.EPOLLIN)
    epoll.register(backdrop["time_update_fd"], select.EPOLLIN)
    epoll.register(backdrop["close_fd"], select.EPOLLIN)
    os.write(backdrop["weather_update_fd"], b"00000000")
    backdrop["running"] = True
    backdrop["thread"] = threading.Thread(target=timer_thread)
    backdrop["thread"].start()
    while backdrop["running"]:
        events = epoll.poll()
        for fd, event in events:
            if fd == display_fd:
                if backdrop["display"].dispatch(block=True) == -1:
                    close(backdrop)
                    break
            elif fd == backdrop["weather_update_fd"]:
                os.read(fd, 8)
                update_weather_info()
            elif fd == backdrop["time_update_fd"]:
                os.read(fd, 8)
                update_time_info()
            elif fd == backdrop["close_fd"]:
                os.read(fd, 8)
                close(backdrop)

if __name__ == "__main__":
    main()
