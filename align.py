import re
import sys
import argparse
import os
from pathlib import Path
from typing import List, Optional

# ---------- Common precompiled regex ----------
BLANK_RE        = re.compile(r'^\s*$')
LINE_COMMENT_RE = re.compile(r'^\s*//')

# ================= Ports formatting =================
PORT_RE = re.compile(
    r'^(?P<indent>\s*)'
    r'(?P<dir>input|output)\s+'
    r'(?:(?P<dtype>reg|wire|logic)(?=\s|\[)\s*)?'
    r'(?P<width>\[[^\]]*\])?'
    r'\s*(?P<name>[A-Za-z_][^\s,;]*)?'
    r'(?P<rest>.*)$'
)

def align_io(lines: List[str]) -> List[str]:
    entries = []
    for line in lines:
        m = PORT_RE.match(line)
        if not m:
            entries.append({'raw': line, 'is_port': False})
            continue
        d = m.groupdict()
        entries.append({
            'is_port': True,
            'indent': d['indent'] or '',
            'dir': d['dir'],
            'dtype': (d.get('dtype') or '').strip() or None,
            'orig_width': d.get('width') or '',
            'name': (d['name'] or '').strip(),
            'rest': d['rest'] or '',
        })

    dtypes = {e['dtype'] for e in entries if e.get('is_port')}
    has_logic = 'logic' in dtypes
    has_wire = 'wire' in dtypes
    has_reg = 'reg' in dtypes

    if has_logic:
        gap_offset = 0
    elif has_wire:
        gap_offset = -1
    elif has_reg:
        gap_offset = -2
    else:
        gap_offset = -6

    def _compact_width(w: str) -> str:
        if not w: return ''
        inside = re.sub(r'\s+', '', w[1:-1])
        return f'[{inside}]'

    def _gap_for(dir_: str, dtype: Optional[str]) -> int:
        if dir_ == 'input':
            if dtype == 'wire':  return 2
            if dtype == 'logic': return 1
            return 8
        if dtype == 'reg':   return 3
        if dtype == 'wire':  return 2
        if dtype == 'logic': return 1
        return 7

    left_areas: List[str] = []
    for e in entries:
        if not e.get('is_port'):
            left_areas.append('')
            continue
        label = e['dir'] + (f" {e['dtype']}" if e['dtype'] else '')
        base_gap = _gap_for(e['dir'], e['dtype'])
        actual_gap = max(0, base_gap + gap_offset)
        gap = ' ' * actual_gap
        width = _compact_width(e['orig_width'])
        left_areas.append(e['indent'] + label + gap + width)

    name_col_base = 0
    for e, left in zip(entries, left_areas):
        if e.get('is_port'):
            name_col_base = max(name_col_base, len(left))

    out_lines: List[str] = []
    for e, left in zip(entries, left_areas):
        if not e.get('is_port'):
            out_lines.append(e['raw'].rstrip())
            continue
        pad_extra = max(0, name_col_base - len(left))
        s = left + (' ' + (' ' * pad_extra) + e['name'] if e['name'] else '')
        rest = e['rest']
        if rest:
            m = re.match(r'\s*,\s*(//.*)?\s*$', rest)
            if m:
                comment = m.group(1) or ''
                s += ',' + (' ' + comment if comment else '')
            else:
                s += rest.rstrip()
        out_lines.append(s.rstrip())
    return out_lines

# ================= Parameter alignment =================
PARAM_LINE_RE = re.compile(r'^(?P<indent>\s*)parameter\s+(?P<left>[^=]+?)\s*=\s*(?P<right>.*)$')

def _format_param_block(block: List[tuple[int, str]]) -> dict[int, str]:
    parsed = []
    max_left_len = 0
    for idx, line in block:
        m = PARAM_LINE_RE.match(line)
        if not m:
            parsed.append((idx, None, line))
            continue
        left = m.group('left').rstrip()
        right = m.group('right').rstrip()
        m2 = re.match(r'^(?P<val>.*?)(?P<comma>,)?\s*(?P<comment>//.*)?\s*$', right)
        val = (m2.group('val') or '').rstrip()
        comma = ',' if m2 and m2.group('comma') else ''
        comment = m2.group('comment') or ''
        parsed.append((idx, {'indent': m.group('indent'), 'left': left, 'val': val, 'comma': comma, 'comment': comment}, None))
        max_left_len = max(max_left_len, len(left))
        
    out: dict[int, str] = {}
    for idx, obj, raw in parsed:
        if obj is None:
            out[idx] = raw.rstrip()
            continue
        pad = ' ' * (max_left_len - len(obj['left']))
        new_line = f"{obj['indent']}parameter {obj['left']}{pad} = {obj['val']}{obj['comma']}"
        if obj['comment']:
            new_line += (' ' if obj['comma'] else '  ') + obj['comment']
        out[idx] = new_line.rstrip()
    return out

def align_parameter_blocks(lines: List[str]) -> List[str]:
    results: dict[int, str] = {}
    i, n = 0, len(lines)
    while i < n:
        if PARAM_LINE_RE.match(lines[i]):
            j, block = i, []
            while j < n and (PARAM_LINE_RE.match(lines[j]) or LINE_COMMENT_RE.match(lines[j]) or BLANK_RE.match(lines[j])):
                block.append((j, lines[j])); j += 1
            results.update(_format_param_block(block)); i = j
        else:
            i += 1
    return [results.get(idx, line.rstrip()) for idx, line in enumerate(lines)]

# ================ localparam alignment ================
LOCALPARAM_LINE_RE = re.compile(
    r'^(?P<indent>\s*)'
    r'localparam\b'
    r'(?P<after_kw>\s+(?:(?:\w+\s+)*)(?:\[[^\]]+\]\s*)?)'
    r'(?P<name>[A-Za-z_]\w*)'
    r'\s*=\s*'
    r'(?P<val>[^;,//]*?)'
    r'(?P<trail>\s*[;,]?)'
    r'(?P<comment>\s*//.*)?$'
)

def _format_localparam_block(block: List[tuple[int, str]]) -> dict[int, str]:
    objs, max_left = [], 0
    for idx, line in block:
        m = LOCALPARAM_LINE_RE.match(line)
        if not m:
            objs.append({'idx': idx, 'keep': line}); continue
        d = m.groupdict()
        after_kw = re.sub(r'\s+', ' ', d['after_kw']).rstrip() if d['after_kw'] else ''
        left = f"{d['indent']}localparam{after_kw} {d['name']}".rstrip()
        max_left = max(max_left, len(left))
        objs.append({'idx': idx, 'left': left, 'val': (d['val'] or '').strip(), 'trail': d['trail'] or ';', 'comment': d['comment'] or ''})
        
    out: dict[int, str] = {}
    for o in objs:
        if 'keep' in o:
            out[o['idx']] = o['keep'].rstrip()
        else:
            pad = ' ' * (max_left - len(o['left']))
            line = f"{o['left']}{pad} = {o['val']}{o['trail']}"
            if o['comment']:
                line += f" {o['comment'].lstrip()}"
            out[o['idx']] = line.rstrip()
    return out

def align_localparam_blocks(lines: List[str]) -> List[str]:
    out = list(lines)
    i, n = 0, len(lines)
    while i < n:
        if lines[i].lstrip().startswith('localparam'):
            j, block = i, []
            while j < n and (lines[j].lstrip().startswith('localparam') or LINE_COMMENT_RE.match(lines[j]) or BLANK_RE.match(lines[j])):
                if lines[j].lstrip().startswith('localparam'):
                    block.append((j, lines[j]))
                j += 1
            if block:
                fmtd = _format_localparam_block(block)
                for k, v in fmtd.items():
                    out[k] = v
                i = j; continue
        i += 1
    return out

# ================= reg/wire/logic decl alignment =================
DECL_RE = re.compile(
    r'^(?P<indent>\s*)(?P<kind>reg|wire|logic)\b'
    r'\s*(?P<width>\[[^\]]*\])?\s*'
    r'(?P<decls>[^;]+)\s*;\s*(?P<comment>//.*)?\s*$'
)

def align_signal_blocks(lines: List[str]) -> List[str]:
    def is_decl_line(line: str) -> bool:
        if bool(re.match(r'^\s*typedef\s+enum\b', line)): return False
        return bool(DECL_RE.match(line))

    out = list(lines)
    n = len(lines)
    GAP_THRESHOLD = 10

    def _format_decl_group(idxs: List[int]) -> None:
        if not idxs: return
        parsed, max_left = [], 0
        for idx in idxs:
            m = DECL_RE.match(lines[idx])
            if not m:
                parsed.append((idx, None)); continue
            kind, width, indent, comment = m.group('kind'), m.group('width') or '', m.group('indent') or '', m.group('comment') or ''
            if width:
                gap = '    ' if kind == 'reg' else (' ' if kind == 'logic' else '  ')
                inside = re.sub(r'\s+', '', width[1:-1])
                left_area = f"{indent}{kind}{gap}[{inside}]"
            else:
                left_area = f"{indent}{kind}"
            parsed.append((idx, {'left': left_area, 'decls': m.group('decls').strip(), 'comment': comment}))
            max_left = max(max_left, len(left_area))
            
        for idx, obj in parsed:
            if obj:
                pad_extra = max(0, max_left - len(obj['left']))
                line = f"{obj['left']} {' ' * pad_extra}{obj['decls']};"
                if obj['comment']: line += f" {obj['comment']}"
                out[idx] = line.rstrip()

    decl_idxs = [i for i, ln in enumerate(lines) if is_decl_line(ln)]
    if not decl_idxs: return out

    blocks, current_block = [], [decl_idxs[0]]
    for i in range(1, len(decl_idxs)):
        if (decl_idxs[i] - decl_idxs[i-1]) > GAP_THRESHOLD:
            blocks.append(current_block)
            current_block = [decl_idxs[i]]
        else:
            current_block.append(decl_idxs[i])
    blocks.append(current_block)

    for b in blocks: _format_decl_group(b)
    return out

# ================ Instance .name(expr) alignment ================
DOT_RE = re.compile(r'^(?P<indent>\s*)\.(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(\s*(?P<expr>.*?)\s*\)\s*(?P<comma>,)?\s*(?P<cmt>//.*)?\s*$')

def align_dot_calls_blocks(lines: List[str]) -> List[str]:
    out = list(lines)
    matches = [(i, DOT_RE.match(ln)) for i, ln in enumerate(lines) if DOT_RE.match(ln)]
    if not matches: return out

    GAP_THRESHOLD = 10
    blocks, current_block = [], [matches[0]]
    for i in range(1, len(matches)):
        if (matches[i][0] - current_block[-1][0] - 1) <= GAP_THRESHOLD:
            current_block.append(matches[i])
        else:
            blocks.append(current_block)
            current_block = [matches[i]]
    blocks.append(current_block)

    for block in blocks:
        max_name = max(len(m.group('name')) for _, m in block)
        for idx, m in block:
            d = m.groupdict()
            pad = ' ' * (max_name - len(d['name']))
            line = f"{d['indent']}.{d['name']}{pad} ({(d['expr'] or '').strip()})"
            if d.get('comma'): line += d['comma']
            if d.get('cmt'):   line += f" {d['cmt']}"
            out[idx] = line.rstrip()
    return out

# ================ Assignment alignment ================
ASSIGN_OP_RE = re.compile(
    r'^(?P<indent>\s*)(?P<left>.*?)\s*'
    r'(?P<op><=|(?<![=!<>])=(?![=<>]))\s*'
    r'(?P<right>.*?)(?P<trail>\s*;)(?P<comment>\s*//.*)?$'
)

def align_assign_ops_in_always_blocks(lines: List[str]) -> List[str]:
    out = list(lines)
    n, i = len(lines), 0
    while i < n:
        if re.match(r'^\s*always(_ff|_comb)?\b', lines[i]):
            depth, found_begin, block_end = 0, False, None
            for j in range(i, n):
                ln = lines[j]
                begins, ends = len(re.findall(r'\bbegin\b', ln)), len(re.findall(r'\bend\b', ln))
                if begins: found_begin = True
                depth += begins - ends
                if found_begin and depth == 0:
                    block_end = j; break
            if block_end is None: i += 1; continue

            inner_start = i
            for k in range(i, block_end + 1):
                if re.search(r'\bbegin\b', lines[k]):
                    inner_start = k + 1; break
            
            idx = inner_start
            while idx < block_end:
                m = ASSIGN_OP_RE.match(lines[idx])
                if not m: idx += 1; continue
                op0, run = m.group('op'), []
                while idx < block_end:
                    mm = ASSIGN_OP_RE.match(lines[idx])
                    if not mm or mm.group('op') != op0 or not mm.group('left').strip(): break
                    run.append((idx, mm)); idx += 1
                
                if len(run) > 1:
                    max_left = max(len(mm.group('indent') + mm.group('left').rstrip()) for _, mm in run)
                    for ridx, mm in run:
                        indent, left = mm.group('indent') or '', mm.group('left').rstrip()
                        pad = ' ' * (max_left - len(indent + left))
                        line = f"{indent}{left}{pad} {mm.group('op')} {mm.group('right').rstrip()}{mm.group('trail') or ';'}"
                        if mm.group('comment'): line += f" {mm.group('comment').lstrip()}"
                        out[ridx] = line.rstrip()
            i = block_end + 1
        else: i += 1
    return out

ASSIGN_START_RE = re.compile(r'^(?P<indent>\s*)(?P<pfx>assign)\s+(?P<left>\S.*?)\s*(?P<op>(?<![=!<>])=(?![=<>]))\s*(?P<rest>.*)$')

def align_consecutive_assigns(lines: List[str]) -> List[str]:
    out, n, i = list(lines), len(lines), 0
    while i < n:
        m = ASSIGN_START_RE.match(lines[i])
        if not m: i += 1; continue
        stmts = []
        while i < n:
            m = ASSIGN_START_RE.match(lines[i])
            if not m: break
            start = j = i
            if ';' not in lines[j]:
                while j + 1 < n and ';' not in lines[j]: j += 1
            stmts.append({'start': start, 'end': j, 'indent': m.group('indent') or '', 'prefix': m.group('pfx'), 'left': m.group('left').rstrip(), 'op': m.group('op'), 'rest': m.group('rest').rstrip()})
            i = j + 1

        if len(stmts) > 1 and len({s['op'] for s in stmts}) == 1:
            max_left = max(len(s['indent'] + s['prefix'] + ' ' + s['left']) for s in stmts)
            for s in stmts:
                pad = ' ' * (max_left - len(s['indent'] + s['prefix'] + ' ' + s['left']))
                out[s['start']] = f"{s['indent']}{s['prefix']} {s['left']}{pad} {s['op']} {s['rest']}".rstrip()
    return out

# ================ Variable Normalization ================
INT_GENVAR_RE = re.compile(r'^(?P<indent>\s*)(?P<kw>integer|genvar)\b\s*(?P<rest>[^;]*?)(?P<trail>\s*;)(?P<comment>//.*)?$')

def align_integer_genvar(lines: List[str]) -> List[str]:
    out = list(lines)
    for i, ln in enumerate(lines):
        m = INT_GENVAR_RE.match(ln)
        if m:
            rest = m.group('rest').strip()
            line = f"{m.group('indent')}{m.group('kw')}{(' ' + rest) if rest else ''}{m.group('trail') or ';'}"
            if m.group('comment'): line += f" {m.group('comment').lstrip()}"
            out[i] = line.rstrip()
    return out

# ================= Processing Core =================

def process_content(text: str, args: argparse.Namespace) -> str:
    lines = [l.expandtabs(4) for l in text.splitlines()]
    
    specific_flags = [args.io, args.param, args.signal, args.inst, args.assign, args.var]
    run_all = not any(specific_flags)
    excluded = args.exclude or []

    if (run_all or args.io) and 'io' not in excluded:
        lines = align_io(lines)
    if (run_all or args.param) and 'param' not in excluded:
        lines = align_parameter_blocks(lines)
        lines = align_localparam_blocks(lines)
    if (run_all or args.signal) and 'signal' not in excluded:
        lines = align_signal_blocks(lines)
    if (run_all or args.inst) and 'inst' not in excluded:
        lines = align_dot_calls_blocks(lines)
    if (run_all or args.assign) and 'assign' not in excluded:
        lines = align_assign_ops_in_always_blocks(lines)
        lines = align_consecutive_assigns(lines)
    if (run_all or args.var) and 'var' not in excluded:
        lines = align_integer_genvar(lines)

    return "\n".join(lines) + '\n'

def main() -> None:
    ap = argparse.ArgumentParser(description="Format Verilog/SystemVerilog files.")
    ap.add_argument('path', nargs='?', help='Input file or directory.')
    ap.add_argument('--io', action='store_true', help='Align IO ports')
    ap.add_argument('--param', action='store_true', help='Align parameters')
    ap.add_argument('--signal', action='store_true', help='Align reg/wire/logic')
    ap.add_argument('--inst', action='store_true', help='Align instance connections')
    ap.add_argument('--assign', action='store_true', help='Align assignments')
    ap.add_argument('--var', action='store_true', help='Align integer/genvar')
    ap.add_argument('--exclude', nargs='+', choices=['io', 'param', 'signal', 'inst', 'assign', 'var'], help='Exclude features')

    args = ap.parse_args()

    if not args.path:
        # Standard input mode
        sys.stdout.write(process_content(sys.stdin.read(), args))
        return

    path = Path(args.path)
    if path.is_file():
        files = [path]
    elif path.is_dir():
        # Recursive search for .sv files
        files = list(path.rglob('*.sv')) + list(path.rglob('*.v'))
    else:
        print(f"Error: Path {args.path} not found.")
        sys.exit(1)

    for f_path in files:
        try:
            with open(f_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            aligned = process_content(content, args)
            
            with open(f_path, 'w', encoding='utf-8') as f:
                f.write(aligned)
            print(f"Aligned: {f_path}")
        except Exception as e:
            print(f"Failed to process {f_path}: {e}")

if __name__ == '__main__':
    main()