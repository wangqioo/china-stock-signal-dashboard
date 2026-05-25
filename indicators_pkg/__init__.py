"""
指标插件加载器
每个插件是一个 .py 文件，需定义：
  META   : dict，描述指标元数据
  compute(df) -> df : 接收 OHLCV DataFrame，返回附加了输出列的 DataFrame
"""
import os, importlib.util, traceback

PLUGIN_DIR = os.path.dirname(__file__)

_registry = {}   # name -> module


def _load_all():
    for fname in sorted(os.listdir(PLUGIN_DIR)):
        if fname.startswith('_') or not fname.endswith('.py'):
            continue
        name = fname[:-3]
        if name in _registry:
            continue
        path = os.path.join(PLUGIN_DIR, fname)
        try:
            spec = importlib.util.spec_from_file_location(f'indicators_pkg.{name}', path)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, 'META') and hasattr(mod, 'compute'):
                _registry[name] = mod
        except Exception:
            traceback.print_exc()


def get_all():
    _load_all()
    return dict(_registry)


def get(name):
    _load_all()
    return _registry.get(name)


def reload_all():
    _registry.clear()
    _load_all()
