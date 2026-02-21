#!/usr/bin/env python3
import re

files = [
    '/app/patrimoine/templates/patrimoine/patrimoine_list.html',
    '/app/patrimoine/templates/patrimoine/intervention_list.html',
    '/app/patrimoine/templates/patrimoine/inspection_list.html'
]

for filepath in files:
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Fix any remaining comparison operators without spaces
    content = content.replace('request.GET.type==code', 'request.GET.type == code')
    content = content.replace('request.GET.statut==code', 'request.GET.statut == code')
    content = content.replace('request.GET.region==region', 'request.GET.region == region')
    content = content.replace('request.GET.etat==code', 'request.GET.etat == code')
    content = content.replace('request.GET.inspecteur==insp', 'request.GET.inspecteur == insp')
    content = content.replace('request.GET.patrimoine==pat', 'request.GET.patrimoine == pat')
    
    # Fix any remaining multi-line if statements (newline + spaces before %})
    content = re.sub(r'({% if[^}]+?)\n\s+(%})', r'\1 \2', content)
    
    with open(filepath, 'w') as f:
        f.write(content)
    
    print('Fixed {}'.format(filepath.split('/')[-1]))
