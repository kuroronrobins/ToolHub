from typing import Any, Dict

FRAME_KEYS = ("frame_name",)


def _find_frame_by_name(page, name: str):
    if not name:
        return None
    frame = page.frame(name=name)
    if frame:
        return frame
    for fr in page.frames:
        if fr.name == name:
            return fr
    raise ValueError(f"Frame '{name}' not found")


def _extract_frame_base(page, sel: Dict[str, Any], base):
    frame_name = sel.get("frame_name")
    if frame_name:
        base = _find_frame_by_name(page, frame_name)
    return base


def _clean_selector(sel: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in sel.items() if k not in FRAME_KEYS}


def resolve_selector(page, sel: Any, base=None):
    """
    sel は:
      - 文字列キー（名前付きセレクタ）
      - dict (role/name/css/xpath/text など)
    """
    if isinstance(sel, str):
        raise ValueError("Named selectors should be resolved by caller (pass the dict).")

    base = base or page
    frame_base = _extract_frame_base(page, sel, base)
    if frame_base is not base:
        sel = _clean_selector(sel)
        base = frame_base
        if not sel:
            raise ValueError("Selector inside frame must specify target element.")

    if "role" in sel and sel.get("by", "role") == "role":
        role = sel["role"]
        name = sel.get("name")
        return base.get_by_role(role, name=name) if name else base.get_by_role(role)

    if sel.get("by") == "text" or "text" in sel:
        text = sel.get("value") or sel.get("text")
        return base.locator(f"text={text}")

    if sel.get("by") == "css" or ("value" in sel and "css" in sel.get("by", "css")):
        value = sel.get("value") or sel.get("css")
        return base.locator(value)

    if sel.get("by") == "xpath":
        return base.locator(f'xpath={sel["value"]}')

    raise ValueError(f"Unsupported selector format: {sel}")


def with_fallback(page, sel_or_list):
    """
    selectors.yml の fallback に対応。最初に一致したものを返し、全滅なら最後の要素でエラー。
    """
    if isinstance(sel_or_list, list):
        last_err = None
        had_success = False
        last_loc = None
        for s in sel_or_list:
            try:
                loc = resolve_selector(page, s)
                had_success = True
                last_loc = loc
                try:
                    if loc.count() > 0:
                        return loc
                except Exception as e:
                    # count() が失敗しても、他候補を試す
                    last_err = e
            except Exception as e:
                last_err = e
        if had_success and last_loc is not None:
            # ヒット0件でも解決できた Locator を返す（wait/click 側で待機・タイムアウトさせる）
            return last_loc
        if last_err:
            raise last_err
        return resolve_selector(page, sel_or_list[-1])
    else:
        return resolve_selector(page, sel_or_list)
