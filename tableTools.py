import re

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