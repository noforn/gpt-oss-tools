import re
from typing import List, Tuple, Dict
from rich.table import Table
from rich.markdown import Markdown

def fix_markdown_tables(text):
    lines = text.split('\n')
    cleaned_lines = []
    in_table = False
    table_rows = []
    
    for i, line in enumerate(lines):
        clean_line = line
        
        stripped = clean_line.strip()
        if len(stripped) > 3 and re.match(r'^[─━═\-_—–−\s]+$', stripped):
            underline_length = len(re.sub(r'\s', '', stripped))
            if underline_length > 0:
                indent = len(clean_line) - len(clean_line.lstrip())
                clean_line = ' ' * indent + '─' * underline_length
        
        stripped_line = clean_line.strip()
        
        if ('|' in stripped_line and 
            stripped_line.count('|') >= 2 and 
            not re.match(r'^\d+\.\s+.*', stripped_line) and
            not re.match(r'^[─━═\-_—–−\s]+$', stripped_line)):
            
            cells = [cell.strip() for cell in stripped_line.split('|')]
            if cells and cells[0] == '':
                cells = cells[1:]
            if cells and cells[-1] == '':
                cells = cells[:-1]
            
            if cells and len([c for c in cells if c.strip()]) > 1:
                if not in_table:
                    in_table = True
                    table_rows = []
                
                clean_row = '| ' + ' | '.join(cells) + ' |'
                table_rows.append(clean_row)
                
                if len(table_rows) == 1 and not any('---' in cell or '===' in cell for cell in cells):
                    separator = '| ' + ' | '.join(['---'] * len(cells)) + ' |'
                    table_rows.append(separator)
            else:
                if in_table:
                    cleaned_lines.extend(table_rows)
                    table_rows = []
                    in_table = False
                cleaned_lines.append(clean_line)
        else:
            if in_table:
                cleaned_lines.extend(table_rows)
                table_rows = []
                in_table = False
            
            cleaned_lines.append(clean_line)
    
    if in_table and table_rows:
        cleaned_lines.extend(table_rows)
    
    return '\n'.join(cleaned_lines)


def linkify_bare_urls(text: str) -> str:
    """Wrap bare URLs in angle brackets so Markdown renders them as links.

    Avoids touching URLs already inside markdown links.
    """
    url_pattern = re.compile(r"(?<!\()\bhttps?://[\w\-._~:/?#\[\]@!$&'()*+,;=%]+\b")
    def replacer(match):
        url = match.group(0)
        return f"<{url}>"
    return url_pattern.sub(replacer, text)


def _is_table_separator(line: str) -> bool:
    stripped = line.strip()
    if '|' not in stripped:
        return False
    cells = [c.strip() for c in stripped.split('|')]
    if cells and cells[0] == '':
        cells = cells[1:]
    if cells and cells[-1] == '':
        cells = cells[:-1]
    if not cells:
        return False
    return all(len(c) > 0 and set(c) <= set('-: ') for c in cells)


def extract_markdown_tables(text: str) -> Tuple[str, List[Dict[str, List[str]]]]:
    """Find simple Markdown tables and return text without them plus parsed tables.

    Returns:
        (clean_text, tables) where tables is a list of dicts: {'header': [...], 'rows': [[...], ...]}
    """
    lines = text.split('\n')
    in_code_block = False
    i = 0
    table_blocks: List[Tuple[int, int, Dict[str, List[str]]]] = []

    while i < len(lines):
        line = lines[i]
        if line.strip().startswith('```'):
            in_code_block = not in_code_block
            i += 1
            continue

        if not in_code_block and '|' in line:
            header_line = line
            j = i + 1
            if j < len(lines) and _is_table_separator(lines[j]):
                def split_cells(s: str) -> List[str]:
                    cells = [c.strip() for c in s.strip().split('|')]
                    if cells and cells[0] == '':
                        cells = cells[1:]
                    if cells and cells[-1] == '':
                        cells = cells[:-1]
                    return cells

                header_cells = split_cells(header_line)
                k = j + 1
                row_cells: List[List[str]] = []
                while k < len(lines):
                    row_line = lines[k]
                    if row_line.strip() == '' or ('|' not in row_line):
                        break
                    row_cells.append(split_cells(row_line))
                    k += 1

                if header_cells and row_cells:
                    table_blocks.append((i, k - 1, {'header': header_cells, 'rows': row_cells}))
                    i = k
                    continue
        i += 1

    if not table_blocks:
        return text, []

    to_skip = set()
    for start, end, _ in table_blocks:
        to_skip.update(range(start, end + 1))

    cleaned_lines = [ln for idx, ln in enumerate(lines) if idx not in to_skip]
    tables = [tb for _, __, tb in table_blocks]
    return '\n'.join(cleaned_lines).strip(), tables


def build_rich_tables(tables: List[Dict[str, List[str]]]) -> List[Table]:
    renderables: List[Table] = []
    for t in tables:
        header = t.get('header', [])
        rows = t.get('rows', [])
        tbl = Table(show_header=True, header_style="bold magenta")
        if header:
            for col in header:
                tbl.add_column(col or "")
        else:
            col_count = len(rows[0]) if rows else 0
            for idx in range(col_count):
                tbl.add_column(f"Col {idx+1}")

        md_inline_pattern = re.compile(r"(\*\*.+?\*\*|__.+?__|\*.+?\*|_.+?_|`.+?`|\[.+?\]\(.+?\)|<https?://[^>]+>)")

        def render_cell(text: str):
            if isinstance(text, str) and md_inline_pattern.search(text):
                return Markdown(text)
            return text

        for r in rows:
            if len(r) < len(tbl.columns):
                r = r + [""] * (len(tbl.columns) - len(r))
            elif len(r) > len(tbl.columns):
                r = r[:len(tbl.columns)]
            tbl.add_row(*[render_cell(c) for c in r])
        renderables.append(tbl)
    return renderables