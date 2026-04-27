import re

# Minimal DSL parser with support for:
# - vars:, selectors:, start:, when <cond>:, whens:, finally:
# - steps: goto/wait/click/choose_file/set_input_files/log and simple blocks
# - blocks: foreach <var> in <array>:, retry <n> every <interval>:, try:/catch:

SEL_LINE = re.compile(r'^(\w+):\s*(.+)$')


def _split_top_level_commas(s: str):
    parts = []
    buf = []
    quote = None
    depth_paren = 0
    depth_brack = 0
    for ch in s:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ('"', "'"):
            quote = ch
            buf.append(ch)
            continue
        if ch == '(':
            depth_paren += 1
            buf.append(ch)
            continue
        if ch == ')':
            depth_paren = max(0, depth_paren - 1)
            buf.append(ch)
            continue
        if ch == '[':
            depth_brack += 1
            buf.append(ch)
            continue
        if ch == ']':
            depth_brack = max(0, depth_brack - 1)
            buf.append(ch)
            continue
        if ch == ',' and depth_paren == 0 and depth_brack == 0:
            parts.append(''.join(buf))
            buf = []
            continue
        buf.append(ch)
    if buf:
        parts.append(''.join(buf))
    return [p.strip() for p in parts if p.strip()]


def parse_selector_value(s: str):
    # Examples:
    #   { by:"text", value:"登録" }
    #   css:"button:has-text('登録'), input[type='button'][value='登録']"
    alts = [a.strip() for a in s.split('|')]
    defs = []
    for a in alts:
        a = a.strip()
        if a.startswith('{') and a.endswith('}'):
            a = a[1:-1].strip()
        kvs = {}
        for part in _split_top_level_commas(a):
            if not part:
                continue
            if ':' in part:
                k, v = part.split(':', 1)
                k = k.strip().strip('"').strip("'")
                v = v.strip().strip('"').strip("'")
                if k:
                    kvs[k] = v
        # normalize shorthands
        if 'text' in kvs and 'by' not in kvs:
            kvs['value'] = kvs['text']
            kvs['by'] = 'text'
        if 'css' in kvs and 'by' not in kvs:
            kvs['value'] = kvs['css']
            kvs['by'] = 'css'
        if 'xpath' in kvs and 'by' not in kvs:
            kvs['value'] = kvs['xpath']
            kvs['by'] = 'xpath'
        if 'role' in kvs and 'by' not in kvs:
            kvs['by'] = 'role'
        kvs.pop('text', None)
        kvs.pop('css', None)
        kvs.pop('xpath', None)
        defs.append(kvs)
    return defs[0] if len(defs) == 1 else defs


def parse(flow_text: str) -> dict:
    lines = [ln.rstrip('\n').rstrip('\r') for ln in flow_text.splitlines()]
    i = 0
    ast = {"vars": {}, "selectors": {}, "start": [], "whens": [], "finally": []}

    def indent_of(s: str) -> int:
        return len(s) - len(s.lstrip(' '))

    def pop() -> str:
        nonlocal i
        s = lines[i]
        i += 1
        return s

    def skip_blanks():
        nonlocal i
        while i < len(lines):
            if not lines[i] or lines[i].strip().startswith('#'):
                i += 1
            else:
                break

    def parse_vars_block(base_indent: int):
        nonlocal i
        while i < len(lines):
            if not lines[i] or lines[i].strip().startswith('#'):
                i += 1
                continue
            cur = indent_of(lines[i])
            if cur <= base_indent:
                break
            raw = lines[i].strip()
            i += 1
            m = SEL_LINE.match(raw)
            if m:
                k, v = m.group(1), m.group(2).strip().strip('"').strip("'")
                ast['vars'][k] = v if not v.startswith('[') else eval(v)

    def parse_selectors_block(base_indent: int):
        nonlocal i
        while i < len(lines):
            if not lines[i] or lines[i].strip().startswith('#'):
                i += 1
                continue
            cur = indent_of(lines[i])
            if cur <= base_indent:
                break
            raw = lines[i].strip()
            i += 1
            m = SEL_LINE.match(raw)
            if not m:
                continue
            name, rhs = m.group(1), m.group(2)
            ast['selectors'][name] = parse_selector_value(rhs)

    def parse_steps(base_indent: int):
        nonlocal i
        steps = []
        while i < len(lines):
            if not lines[i] or lines[i].strip().startswith('#'):
                i += 1
                continue
            cur = indent_of(lines[i])
            if cur < base_indent:
                break
            if cur > base_indent:
                i += 1
                continue
            stmt_line = pop().strip()
            if stmt_line.startswith('foreach ') and stmt_line.endswith(':'):
                header = stmt_line[len('foreach '):-1].strip()
                var, _, arr = header.partition(' in ')
                var = var.strip(); arr = arr.strip()
                nested = parse_steps(base_indent + 2)
                steps.append({'foreach': {'var': var, 'arr': arr, 'steps': nested}})
                continue
            if stmt_line.startswith('retry ') and stmt_line.endswith(':'):
                body = stmt_line[len('retry '):-1].strip()
                tries_part, _, interval_part = body.partition(' every ')
                nested = parse_steps(base_indent + 2)
                steps.append({'retry': {'tries': tries_part.strip(), 'interval': interval_part.strip(), 'steps': nested}})
                continue
            if stmt_line == 'try:':
                try_steps = parse_steps(base_indent + 2)
                catch_steps = []
                if i < len(lines) and indent_of(lines[i]) == base_indent and lines[i].strip() == 'catch:':
                    i += 1
                    catch_steps = parse_steps(base_indent + 2)
                steps.append({'try': {'steps': try_steps, 'catch': catch_steps}})
                continue
            steps.append(stmt_line)
        return steps

    def parse_whens_yaml(base_indent: int):
        nonlocal i
        whens = []
        while i < len(lines):
            skip_blanks()
            if i >= len(lines):
                break
            cur = indent_of(lines[i])
            if cur <= base_indent:
                break
            line = lines[i].strip()
            if not line.startswith('-'):
                i += 1
                continue
            m = re.match(r'^-\s*condition:\s*(.+)$', line)
            if not m:
                i += 1
                continue
            cond = m.group(1).strip().rstrip(':')
            i += 1
            skip_blanks()
            steps = []
            if i < len(lines) and lines[i].strip().startswith('steps:'):
                steps_indent = indent_of(lines[i]) + 2
                i += 1
                steps = parse_steps(steps_indent)
            whens.append({'condition': cond, 'steps': steps})
        return whens

    while i < len(lines):
        skip_blanks()
        if i >= len(lines):
            break
        line = pop()
        if not line or line.strip().startswith('#'):
            continue
        if line.startswith('vars:'):
            base = indent_of(line)
            parse_vars_block(base)
            continue
        if line.startswith('selectors:'):
            base = indent_of(line)
            parse_selectors_block(base)
            continue
        if line.startswith('start:'):
            base = indent_of(line) + 2
            ast['start'] = parse_steps(base)
            continue
        if line.startswith('when '):
            cond = line[len('when '):].strip().rstrip(':')
            base = indent_of(line) + 2
            ast['whens'].append({'condition': cond, 'steps': parse_steps(base)})
            continue
        if line.startswith('whens:'):
            base = indent_of(line)
            ast['whens'].extend(parse_whens_yaml(base))
            continue
        if line.startswith('finally:'):
            base = indent_of(line) + 2
            ast['finally'] = parse_steps(base)
            continue
    return ast
