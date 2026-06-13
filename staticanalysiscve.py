import os
import re
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon, Ellipse, Patch

plt.switch_backend('Agg')

# -------------------------- Global Configuration --------------------------
TARGET_VARS = {"p", "pLeft", "pRight", "pRoot"}
BLACK_LIST = {
    "void", "sqlite3", "db", "mallocFailed", "Expr", "ExprUseXList",
    "pSelect", "flags", "EP_UseXList", "nHeight", "SQLITE_MAX_EXPR_DEPTH",
    "endif", "sqlite3PExpr", "pParse", "Parse", "op", "memset",
    "sqlite3DbMallocRawNN", "sqlite3ExprAttachSubtrees", "sqlite3ExprCheckHeight",
    "assert", "sizeof", "xff", "iAgg"
}

# -------------------------- Utility Functions --------------------------
def filter_comments(text):
    pat = r'/\*[\s\S]*?\*/|//[^\n]*'
    return re.sub(pat, '', text, flags=re.DOTALL)

def split_valid_statements(code):
    stmts = re.split(r'([;{}])', code)
    res = []
    in_body = False
    buf = ""
    for s in stmts:
        s = s.strip()
        if not s:
            continue
        buf += s
        if s == "{":
            in_body = True
            buf = ""
            continue
        if s == "}":
            in_body = False
            buf = ""
            continue
        if in_body and len(buf) > 1:
            res.append(buf)
        buf = ""
    return res

def extract_malloc(stmt):
    pat = r'(\w+)\s*=\s*sqlite3DbMallocRawNN\s*\('
    res = re.findall(pat, stmt)
    return [v for v in res if v in TARGET_VARS]

def extract_free(stmt):
    pat = r'sqlite3ExprDelete\s*\(.*?,\s*(\w+)\s*\)'
    res = re.findall(pat, stmt)
    return [v for v in res if v in TARGET_VARS]

def extract_use(stmt):
    if re.search(r'sqlite3ExprDelete', stmt):
        return []
    uses = set()
    struct_vars = re.findall(r'(\w+)->\w+', stmt)
    for v in struct_vars:
        if v in TARGET_VARS:
            uses.add(v)
    for word in re.findall(r'[a-zA-Z_]\w+', stmt):
        if word in TARGET_VARS:
            uses.add(word)
    return [f"use {v}" for v in uses]

def extract_alias(stmt):
    pat = r'(\w+)\s*=\s*(\w+)\s*;'
    m = re.search(pat, stmt)
    if m:
        a, b = m.groups()
        if a in TARGET_VARS and b in TARGET_VARS:
            return f"alias {a} -> {b}"
    return None

# -------------------------- Drawing Function (fully aligned with original: spacing, color scheme, stroke width) --------------------------
def draw_graph(ops_list):
    max_draw = 20
    ops = ops_list[:max_draw]

    fig = plt.figure(figsize=(16, 8))
    ax = plt.gca()
    ax.set_xlim(-1, len(ops) * 2.5)   # Original spacing: center interval = 2.5
    ax.set_ylim(-2, 2)
    ax.axis('off')

    var_id_map = {}
    next_id = 1
    base_h = 0.6
    rect_w = 1.2
    ellipse_w = 0.5
    tri_w = 1.2
    trap_w = 1.2

    for idx, op in enumerate(ops):
        # X coordinate of shape center, strictly follows original spacing
        x = idx * 2.5
        y = 0

        # malloc: ellipse with lightcoral fill + linewidth=1.5 border
        if op.startswith("malloc"):
            var = op.split()[1]
            if var not in var_id_map:
                var_id_map[var] = next_id
                next_id += 1
            vid = var_id_map[var]
            ellipse = Ellipse((x, y), width=ellipse_w, height=base_h,
                              facecolor='lightcoral', edgecolor='black', linewidth=1.5)
            ax.add_patch(ellipse)
            ax.text(x, y, f"{vid}", ha="center", va="center", fontsize=14, weight="bold")

        # free: triangle with lightgreen fill, thickened border linewidth=2
        elif op.startswith("free"):
            var = op.split()[1]
            if var not in var_id_map:
                var_id_map[var] = next_id
                next_id += 1
            vid = var_id_map[var]
            tri = Polygon([
                (x - tri_w / 2, y - base_h / 2),
                (x + tri_w / 2, y - base_h / 2),
                (x, y + base_h / 2)
            ], facecolor='lightgreen', edgecolor='black', linewidth=2)
            ax.add_patch(tri)
            ax.text(x, y, f"{vid}", ha="center", va="center", fontsize=14, weight="bold")

        # use: rectangle with lightblue fill + linewidth=1.5 border
        elif op.startswith("use"):
            var = op.split()[1]
            if var not in var_id_map:
                var_id_map[var] = next_id
                next_id += 1
            vid = var_id_map[var]
            rect = Rectangle((x - rect_w / 2, y - base_h / 2),
                             width=rect_w, height=base_h,
                             facecolor='lightblue', edgecolor='black', linewidth=1.5)
            ax.add_patch(rect)
            ax.text(x, y, f"{vid}", ha="center", va="center", fontsize=14, weight="bold")

        # alias: trapezoid with ivory fill + linewidth=1.5 border
        elif op.startswith("alias"):
            m = re.search(r'alias\s+(\w+)->', op)
            if m:
                var = m.group(1)
                if var not in var_id_map:
                    var_id_map[var] = next_id
                    next_id += 1
                vid = var_id_map[var]
                trap = Polygon([
                    (x - trap_w / 2, y - base_h / 2),
                    (x + trap_w / 2, y - base_h / 2),
                    (x + trap_w / 4, y + base_h / 2),
                    (x - trap_w / 4, y + base_h / 2)
                ], facecolor='ivory', edgecolor='black', linewidth=1.5)
                ax.add_patch(trap)
                ax.text(x, y, f"{vid}", ha="center", va="center", fontsize=14, weight="bold")

        # Step number label at bottom
        ax.text(x, -1.3, f"Step{idx + 1}", ha="center", fontsize=8, color="gray")

    # Legend
    leg = [
        Patch(fc='lightcoral', ec='black', lw=1.5, label='Memory Allocation (malloc)'),
        Patch(fc='lightblue', ec='black', lw=1.5, label='Memory Usage'),
        Patch(fc='lightgreen', ec='black', lw=2, label='Free / sqlite3ExprDelete'),
        Patch(fc='ivory', ec='black', lw=1.5, label='Pointer Alias')
    ]
    ax.legend(handles=leg, loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=4, fontsize=10)
    plt.title("Static Analysis CVE UAF Visual Feature Diagram", fontsize=14, weight="bold")
    plt.tight_layout()
    plt.savefig("static.png", dpi=300, bbox_inches="tight")
    plt.close()
    print("\n✅ static.png generated successfully (spacing, color scheme and stroke width fully aligned with original version)")

# -------------------------- Main Entry Logic --------------------------
def main():
    file_path = r"D:\zhang\uaf\cppsnippetcve.txt"
    if not os.path.exists(file_path):
        print("Error: Target file does not exist ->", file_path)
        return

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        raw_code = f.read()

    code_no_comment = filter_comments(raw_code)
    stmts = split_valid_statements(code_no_comment)

    ops_seq = []
    for stmt in stmts:
        mallocs = extract_malloc(stmt)
        for v in mallocs:
            ops_seq.append(f"malloc {v}")
        free_vars = extract_free(stmt)
        for v in free_vars:
            ops_seq.append(f"free {v}")
        alias = extract_alias(stmt)
        if alias:
            ops_seq.append(alias)
        uses = extract_use(stmt)
        for u in uses:
            ops_seq.append(u)

    print("==== Extracted UAF Operation Sequence ====")
    for idx, item in enumerate(ops_seq, 1):
        print(f"{idx}. {item}")

    if ops_seq:
        draw_graph(ops_seq)

if __name__ == "__main__":
    main();
