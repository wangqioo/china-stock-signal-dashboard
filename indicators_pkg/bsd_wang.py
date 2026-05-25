"""波段王：K/D 动能柱"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from indicators import calc_bsd_wang, calc_main_signals

META = {
    "name":   "波段王",
    "id":     "bsd_wang",
    "panel":  "sub",           # 独立副图
    "height": 0.26,            # 占图表区比例
    "range":  [0, 100],        # 纵轴固定范围
    "outputs": [
        {"col": "K", "type": "line", "color": "#ef5350", "width": 1},
        {"col": "D", "type": "line", "color": "#26a69a", "width": 1},
        # K/D 之间的色块由前端特殊处理（stickline）
        {"col": "K", "col2": "D", "type": "stickline",
         "color_bull": "#CC0000", "color_bear": "#00AA00"},
        {"col": "波段王_多", "type": "marker", "position": "belowBar",
         "color": "#FF3030", "shape": "arrowUp",   "size": 1.0},
        {"col": "波段王_空", "type": "marker", "position": "aboveBar",
         "color": "#00DD00", "shape": "arrowDown", "size": 1.0},
    ],
    "hlines": [
        {"value": 90, "color": "#FFD700", "width": 1},
    ],
}


def compute(df):
    return calc_bsd_wang(calc_main_signals(df))
