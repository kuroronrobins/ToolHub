
import os, re, pathlib
from datetime import datetime

VAR_RE = re.compile(r"\$\{([^}]+)\}")

def _fn_now():
    return datetime.now().isoformat(timespec="seconds")

def _fn_basename(p): return pathlib.Path(p).name
def _fn_dirname(p):  return str(pathlib.Path(p).parent)
def _fn_extname(p):  return pathlib.Path(p).suffix

BUILTINS = {
    "now": _fn_now,
    "basename": _fn_basename,
    "dirname": _fn_dirname,
    "extname": _fn_extname,
}

def eval_expr(text: str, ctx: dict):
    def repl(m):
        expr = m.group(1).strip()
        # 関数呼び出し or 変数参照（最小実装）
        if "(" in expr and expr.endswith(")"):
            name = expr[:expr.index("(")].strip()
            arg = expr[expr.index("(")+1:-1].strip()
            fn = BUILTINS.get(name)
            val = ctx.get(arg) if arg and arg in ctx else arg
            return str(fn() if not arg else fn(val)) if fn else ""
        # ドット参照/配列は最小対応（files など）
        parts = expr.split(".")
        cur = ctx
        for p in parts:
            if "[" in p and p.endswith("]"):
                key, idx = p[:p.index("[")], int(p[p.index("[")+1:-1])
                cur = cur[key][idx]
            else:
                cur = cur[p]
        return str(cur)
    return VAR_RE.sub(repl, text)

def merge_vars(flow_vars: dict, cli_vars: dict) -> dict:
    out = dict(flow_vars or {})
    out.update(cli_vars or {})
    return out
