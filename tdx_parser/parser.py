"""
TDX 公式解析器（简单版）

支持语法：
  VAR: EXPR;                        普通赋值
  NAME, EXPR, COLORREF, THICK;      POLYLINE 绘图行（输出折线）
  DRAWTEXT(cond, price, text);      文字标记
  STICKLINE(cond, p1, p2, w, e);    色块柱
  COLOR 后缀（COLORRED/COLORGREEN/COLORYELLOW 等）

不支持：循环、自定义函数、FINANCE/CAPITAL 系列
"""
import re
import textwrap
import pandas as pd
from .functions import BUILTIN_FUNCS

# TDX 颜色常量 → CSS
COLOR_MAP = {
    'COLORRED':     '#FF0000',
    'COLORGREEN':   '#00FF00',
    'COLORYELLOW':  '#FFFF00',
    'COLORBLUE':    '#0000FF',
    'COLORWHITE':   '#FFFFFF',
    'COLORBLACK':   '#000000',
    'COLORMAGENTA': '#FF00FF',
    'COLORCYAN':    '#00FFFF',
    'COLORLIRED':   '#FF6666',
    'COLORLIGRAY':  '#AAAAAA',
    'COLORLIBLUE':  '#6699FF',
    'COLORLIGREEN': '#66FF66',
    'COLORBA':      '#FF8C00',  # 暗橙（慧赢常用）
}

DRAW_KEYWORDS = {'DRAWTEXT', 'STICKLINE', 'DRAWICON', 'DRAWNUMBER',
                 'DRAWLINE', 'DRAWKLINE', 'PLOYLINE', 'POLYLINE'}


class TDXParser:
    def __init__(self, source: str):
        self.source  = source
        self.stmts   = []   # 解析出的语句列表
        self.outputs = []   # META outputs
        self.hlines  = []   # 水平参考线
        self._parse()

    # ── 预处理 ────────────────────────────────────────────
    def _clean(self, src):
        # 去注释（{...} 和 //...）
        src = re.sub(r'\{[^}]*\}', '', src)
        src = re.sub(r'//[^\n]*', '', src)
        # 统一换行、去多余空白
        src = src.replace('\r\n', '\n').replace('\r', '\n')
        return src.strip()

    def _split_statements(self, src):
        """按分号拆语句，保留多行"""
        parts = []
        buf = []
        for line in src.split('\n'):
            line = line.strip()
            if not line:
                continue
            buf.append(line)
            joined = ' '.join(buf)
            if joined.rstrip().endswith(';'):
                parts.append(joined.rstrip(';').strip())
                buf = []
        if buf:
            parts.append(' '.join(buf).rstrip(';').strip())
        return [p for p in parts if p]

    # ── 主解析 ────────────────────────────────────────────
    def _parse(self):
        src = self._clean(self.source)
        for stmt in self._split_statements(src):
            self._parse_stmt(stmt)

    def _parse_stmt(self, stmt):
        stmt = stmt.strip()
        if not stmt:
            return

        upper = stmt.upper()

        # DRAWTEXT(cond, price, 'text'), COLOR...
        if upper.startswith('DRAWTEXT'):
            m = re.match(r'DRAWTEXT\s*\((.+),\s*(.+),\s*[\'"](.+)[\'"]\s*\)', stmt, re.I)
            if m:
                cond_expr, price_expr, text = m.group(1), m.group(2), m.group(3)
                color = self._extract_color(stmt) or '#FFFFFF'
                self.stmts.append({
                    'type': 'drawtext', 'cond': cond_expr,
                    'price': price_expr, 'text': text, 'color': color,
                })
            return

        # STICKLINE(cond, p1, p2, width, empty)
        if upper.startswith('STICKLINE'):
            m = re.match(r'STICKLINE\s*\((.+),(.+),(.+),(.+),(.+)\)', stmt, re.I)
            if m:
                color = self._extract_color(stmt) or '#FF0000'
                self.stmts.append({
                    'type': 'stickline',
                    'cond': m.group(1).strip(), 'p1': m.group(2).strip(),
                    'p2':  m.group(3).strip(),  'width': m.group(4).strip(),
                    'color': color,
                })
            return

        # 赋值：VAR:EXPR 或 VAR:=EXPR（中间变量）
        m = re.match(r'^([A-Z_][A-Z0-9_]*)\s*:=?\s*(.+)$', stmt, re.I)
        if m:
            varname  = m.group(1).upper()
            expr_str = m.group(2).strip()
            # 提取颜色和粗细后缀
            color, expr_str = self._strip_color(expr_str)
            thick, expr_str = self._strip_thick(expr_str)
            nodraw = varname.startswith('VAR') or ':=' in stmt
            self.stmts.append({
                'type': 'assign', 'var': varname, 'expr': expr_str,
                'color': color, 'thick': thick, 'nodraw': nodraw,
            })
            return

        # 输出行：NAME,EXPR,COLOR,THICK（逗号分隔，4段）
        parts = [p.strip() for p in stmt.split(',')]
        if len(parts) >= 2:
            varname  = parts[0].upper()
            expr_str = parts[1].strip() if len(parts) > 1 else ''
            color    = COLOR_MAP.get(parts[2].upper().strip(), parts[2].strip()) if len(parts) > 2 else '#FFFFFF'
            try:
                thick = int(parts[3].strip()) if len(parts) > 3 else 1
            except ValueError:
                thick = 1
            self.stmts.append({
                'type': 'assign', 'var': varname, 'expr': expr_str,
                'color': color, 'thick': thick, 'nodraw': False,
            })

    def _extract_color(self, stmt):
        for k, v in COLOR_MAP.items():
            if k in stmt.upper():
                return v
        m = re.search(r'COLOR([0-9A-Fa-f]{6})', stmt, re.I)
        if m:
            return '#' + m.group(1).upper()
        return None

    def _strip_color(self, expr):
        color = None
        for k, v in COLOR_MAP.items():
            if expr.upper().endswith(',' + k):
                color = v
                expr = expr[:-(len(k) + 1)].strip().rstrip(',').strip()
                break
        if color is None:
            m = re.search(r',\s*COLOR([0-9A-Fa-f]{6})\s*$', expr, re.I)
            if m:
                color = '#' + m.group(1).upper()
                expr = expr[:m.start()].strip()
        return color, expr

    def _strip_thick(self, expr):
        thick = 1
        m = re.search(r',\s*(\d+)\s*$', expr)
        if m:
            thick = int(m.group(1))
            expr = expr[:m.start()].strip()
        return thick, expr

    # ── 执行：把语句作用于 DataFrame ─────────────────────
    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        result = df.copy()
        env = {
            'OPEN':   result['open'].astype(float),
            'HIGH':   result['high'].astype(float),
            'LOW':    result['low'].astype(float),
            'CLOSE':  result['close'].astype(float),
            'VOLUME': result.get('volume', pd.Series(0, index=result.index)).astype(float),
            **BUILTIN_FUNCS,
        }

        for stmt in self.stmts:
            try:
                if stmt['type'] == 'assign':
                    val = self._eval(stmt['expr'], env)
                    env[stmt['var']] = val
                    result[stmt['var']] = val

                elif stmt['type'] == 'drawtext':
                    cond  = self._eval(stmt['cond'],  env)
                    price = self._eval(stmt['price'], env)
                    col   = f"_TEXT_{stmt['text'][:8]}"
                    result[col] = cond
                    result[col + '_PRICE'] = price

                elif stmt['type'] == 'stickline':
                    cond = self._eval(stmt['cond'], env)
                    p1   = self._eval(stmt['p1'],   env)
                    p2   = self._eval(stmt['p2'],   env)
                    result['_STICK_COND']  = cond
                    result['_STICK_P1']    = p1
                    result['_STICK_P2']    = p2
                    result['_STICK_COLOR'] = stmt['color']

            except Exception as e:
                print(f"[TDX] 执行失败 {stmt}: {e}")

        return result

    def _eval(self, expr: str, env: dict):
        # 替换 TDX 特有写法
        expr = re.sub(r'\bAND\b', ' & ',  expr, flags=re.I)
        expr = re.sub(r'\bOR\b',  ' | ',  expr, flags=re.I)
        expr = re.sub(r'\bNOT\b', '~',    expr, flags=re.I)
        # 大写化函数名（已在 env 里）
        try:
            return eval(expr, {"__builtins__": {}}, env)
        except Exception as e:
            raise ValueError(f"eval失败: {expr!r} → {e}")

    # ── 生成 META outputs ────────────────────────────────
    def build_meta_outputs(self):
        outputs = []
        for stmt in self.stmts:
            if stmt['type'] == 'assign' and not stmt.get('nodraw') and stmt.get('color'):
                outputs.append({
                    'col':   stmt['var'],
                    'type':  'line',
                    'color': stmt['color'],
                    'width': stmt.get('thick', 1),
                })
            elif stmt['type'] == 'drawtext':
                col = f"_TEXT_{stmt['text'][:8]}"
                outputs.append({
                    'col':      col,
                    'type':     'marker',
                    'text':     stmt['text'],
                    'color':    stmt['color'] or '#FFFFFF',
                    'position': 'aboveBar',
                    'shape':    'circle',
                    'size':     1.0,
                })
            elif stmt['type'] == 'stickline':
                outputs.append({
                    'col':   '_STICK_COND',
                    'col_p1': '_STICK_P1',
                    'col_p2': '_STICK_P2',
                    'type':  'stickline',
                    'color': stmt['color'],
                })
        return outputs

    # ── 生成插件 .py 文件内容 ────────────────────────────
    def to_plugin_source(self, plugin_id: str, plugin_name: str, panel='sub') -> str:
        outputs_repr = repr(self.build_meta_outputs())
        escaped = self.source.replace('\\', '\\\\').replace('"""', '\\"\\"\\"')
        return textwrap.dedent(f'''\
            """自动生成插件：{plugin_name}"""
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            import pandas as pd
            from tdx_parser import TDXParser

            _SOURCE = """{escaped}"""

            META = {{
                "name":    "{plugin_name}",
                "id":      "{plugin_id}",
                "panel":   "{panel}",
                "outputs": {outputs_repr},
                "hlines":  [],
            }}

            def compute(df: pd.DataFrame) -> pd.DataFrame:
                return TDXParser(_SOURCE).compute(df)
        ''')
