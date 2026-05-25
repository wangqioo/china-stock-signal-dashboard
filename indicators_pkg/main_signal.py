"""主图指标：破浪/空仓信号（黄点/绿点）"""
import numpy as np
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from indicators import calc_main_signals

META = {
    "name":     "主图信号",
    "id":       "main_signal",
    "panel":    "main",        # 画在主图
    "outputs": [
        {"col": "M1",  "type": "line",   "color": "#FFD700", "width": 1, "color_rising": "#FF00FF"},
        {"col": "M2",  "type": "line",   "color": "#FFD700", "width": 1, "color_rising": "#FF00FF"},
        {"col": "M3",  "type": "line",   "color": "#FFD700", "width": 2, "color_rising": "#FF00FF"},
        {"col": "M4",  "type": "line",   "color": "#FFD700", "width": 2, "color_rising": "#FF00FF"},
        {"col": "M5",  "type": "line",   "color": "#FFD700", "width": 3, "color_rising": "#FF00FF"},
        {"col": "支撑", "type": "line",   "color": "#00AAFF", "width": 2},
        {"col": "破浪", "type": "marker", "position": "belowBar", "color": "#FFD700", "shape": "circle", "size": 1.2},
        {"col": "空仓", "type": "marker", "position": "aboveBar", "color": "#00CC00", "shape": "circle", "size": 1.2},
    ],
}


def compute(df):
    return calc_main_signals(df)
