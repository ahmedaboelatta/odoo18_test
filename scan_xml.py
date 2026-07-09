import os, re, xml.etree.ElementTree as ET

xml_files = []
for root, dirs, files in os.walk(r'D:\Alezdhar Company\OneDrive\Documents\GitHub\odoo18_test\bird_connector'):
    for f in files:
        if f.endswith('.xml'):
            xml_files.append(os.path.join(root, f))

entities = {'amp', 'lt', 'gt', 'quot', 'apos'}
issues = []

for filepath in xml_files:
    rel = os.path.relpath(filepath, r'D:\Alezdhar Company\OneDrive\Documents\GitHub\odoo18_test')
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            if '&' in stripped:
                for m in re.finditer(r'&([#A-Za-z0-9]+);?', stripped):
                    name = m.group(1)
                    full = m.group(0)
                    if name not in entities and not full.endswith(';'):
                        issues.append(f'{rel}:{lineno}: Unescaped ampersand: {stripped}')
                        break
            if re.search(r'<[A-Za-z][^>]*\s[A-Za-z-]+=([^"\'\s>]*)', stripped):
                if not re.search(r'<[A-Za-z][^>]*\s[A-Za-z-]+="[^"]*"', stripped) and not re.search(r"<[A-Za-z][^>]*\s[A-Za-z-]+='[^']*'", stripped):
                    issues.append(f'{rel}:{lineno}: Possible missing quotes in attribute: {stripped}')
            ctrl = re.findall(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', stripped)
            if ctrl:
                issues.append(f'{rel}:{lineno}: Invalid control characters: {repr(ctrl)} in line: {stripped}')
    except Exception as e:
        issues.append(f'{rel}: Error reading file: {e}')
    try:
        ET.parse(filepath)
    except ET.ParseError as e:
        issues.append(f'{rel}: XML Parse Error: {e}')

for issue in issues:
    print(issue)
