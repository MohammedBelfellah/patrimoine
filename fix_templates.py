#!/usr/bin/env python3
import re

print("Fixing templates...")

# Fix patrimoine_list.html
with open('/app/patrimoine/templates/patrimoine/patrimoine_list.html', 'r') as f:
    content = f.read()

# Replace the multi-line if statement pattern for region
content = re.sub(
    r'(<option value="{{ region\.id_region }}" {\% if request\.GET\.region == region\.id_region\|stringformat:"s"\s*%\})selected',
    r'\1selected',
    content,
    flags=re.MULTILINE
)

# More direct replacement using literal newline
old_region = '''<option value="{{ region.id_region }}" {% if request.GET.region == region.id_region|stringformat:"s"
                %}selected{% endif %}>'''
new_region = '''<option value="{{ region.id_region }}" {% if request.GET.region == region.id_region|stringformat:"s" %}selected{% endif %}>'''

if old_region in content:
    content = content.replace(old_region, new_region)
    print("  - Fixed region filter in patrimoine_list.html")
else:
    print("  - Region filter pattern not found (may already be fixed)")

with open('/app/patrimoine/templates/patrimoine/patrimoine_list.html', 'w') as f:
    f.write(content)

# Fix inspection_list.html
with open('/app/patrimoine/templates/patrimoine/inspection_list.html', 'r') as f:
    content = f.read()

old_pat = '''<option value="{{ pat.id_patrimoine }}" {% if
                                request.GET.patrimoine == pat.id_patrimoine|stringformat:"s" %}selected{% endif %}>'''
new_pat = '''<option value="{{ pat.id_patrimoine }}" {% if request.GET.patrimoine == pat.id_patrimoine|stringformat:"s" %}selected{% endif %}>'''

if old_pat in content:
    content = content.replace(old_pat, new_pat)
    print("  - Fixed patrimoine filter in inspection_list.html")
else:
    print("  - Patrimoine filter pattern not found (may already be fixed)")

with open('/app/patrimoine/templates/patrimoine/inspection_list.html', 'w') as f:
    f.write(content)

print("Templates fixed successfully!")
