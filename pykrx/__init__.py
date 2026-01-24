import importlib.resources as resources
import platform

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

from . import bond, stock

os = platform.system()

if os == "Darwin":
    plt.rc("font", family="AppleGothic")

else:
    with resources.path("pykrx", "NanumBarunGothic.ttf") as font_path:
        fe = fm.FontEntry(fname=str(font_path), name="NanumBarunGothic")
        fm.fontManager.ttflist.insert(0, fe)
        plt.rc("font", family=fe.name)

plt.rcParams["axes.unicode_minus"] = False

__all__ = ["bond", "stock"]

__version__ = "1.0.51"
