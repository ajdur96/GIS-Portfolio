"""Builds index.html from the Experience Builder export (export2.json)."""
import json, re, html
from html.parser import HTMLParser

data = json.load(open('export2.json'))
pagesById = {p['id']: p for p in data['pages']}
dataSources = data['ds']

ALLOWED = {'p', 'br', 'strong', 'em', 'u', 'a', 'ul', 'ol', 'li', 'h2'}
JUNK = re.compile('[﻿​]')


class Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED:
            return
        if tag == 'a':
            href = dict(attrs).get('href', '') or ''
            if re.fullmatch(r'page_\d+', href):
                self.out.append(f'<a href="#/{href}">')
            else:
                self.out.append(f'<a href="{html.escape(href)}" target="_blank" rel="noopener">')
        elif tag == 'br':
            self.out.append('<br>')
        else:
            self.out.append(f'<{tag}>')

    def handle_endtag(self, tag):
        if tag in ALLOWED and tag != 'br':
            self.out.append(f'</{tag}>')

    def handle_data(self, d):
        self.out.append(html.escape(JUNK.sub('', d), quote=False))


def sanitize(raw):
    s = Sanitizer()
    s.feed(raw)
    out = ''.join(s.out)
    out = re.sub(r'<p>(\s|<br>|&nbsp;|\xa0)*</p>', '', out)
    return out.strip()


def plainText(raw):
    t = re.sub(r'</(p|li|h2)>|<br\s*/?>', '\n', raw)
    t = html.unescape(re.sub(r'<[^>]+>', '', t))
    t = JUNK.sub('', t).replace('\xa0', ' ')
    return '\n'.join(l.strip() for l in t.split('\n') if l.strip())


def buildBlocks(page):
    """Turn a page's flat widget list into typed blocks."""
    blocks, lastText = [], None
    for it in page['items']:
        kind = it['t']
        if kind == 'T':
            txt = plainText(it['html'])
            if not txt or txt == lastText or txt == 'SPACE SAVER':
                continue
            lastText = txt
            lines = txt.split('\n')
            if txt.startswith('Fig'):
                blocks.append({'type': 'caption', 'html': sanitize(it['html'])})
            elif lines[0].lower().startswith(('key skills developed', 'skills developed')):
                blocks.append({'type': 'skills', 'items': lines[1:]})
            elif re.match(r'(Semester|Timeframe):', lines[0]):
                blocks.append({'type': 'meta', 'items': lines})
            elif len(lines) == 1 and len(txt) <= 45 and not txt.endswith('.'):
                blocks.append({'type': 'heading', 'text': txt})
            else:
                blocks.append({'type': 'text', 'html': sanitize(it['html'])})
        elif kind == 'I':
            if not it.get('src'):
                continue
            link = it.get('link') or {}
            linkPage = link.get('value') if link.get('linkType') == 'PAGE' else None
            img = {'src': it['src'], 'alt': it.get('alt', ''), 'page': linkPage}
            if blocks and blocks[-1]['type'] == 'images' and not linkPage and not blocks[-1]['items'][-1]['page']:
                blocks[-1]['items'].append(img)
            else:
                blocks.append({'type': 'images', 'items': [img]})
            lastText = None
        elif kind == 'E':
            blocks.append({'type': 'embed', 'src': it['src'].strip()})
        elif kind == 'M':
            ids = [dataSources[d] for d in it['ds'] if d in dataSources]
            if ids:
                blocks.append({'type': 'map', 'webmap': ids[0]})
    return blocks


# Pages to include: visible hubs and their visible children (mirrors the live site's navigation)
nav = []
included = {}
for entry in data['order']:
    (parentId, childIds), = entry.items()
    parent = pagesById[parentId]
    if not parent['visible']:
        continue
    kids = [c for c in childIds if pagesById[c]['visible']]
    nav.append({'id': parentId, 'label': parent['label'], 'children': [{'id': c, 'label': pagesById[c]['label']} for c in kids]})
    for pid in [parentId] + kids:
        included[pid] = {'id': pid, 'label': pagesById[pid]['label'], 'blocks': buildBlocks(pagesById[pid])}
    # Some hub images on the live site are missing their page link; reconnect by matching the card title
    hubBlocks = included[parentId]['blocks']
    for i, b in enumerate(hubBlocks[:-1]):
        nxt = hubBlocks[i + 1]
        if b['type'] == 'images' and len(b['items']) == 1 and not b['items'][0]['page'] and nxt['type'] == 'heading':
            match = [c for c in kids if pagesById[c]['label'].lower().endswith(nxt['text'].lower())]
            if match:
                b['items'][0]['page'] = match[0]

# Homepage cards link to the three sections (the live site uses click areas, not image links)
homeTargets = {'MSGIS Projects': 'page_6', 'Internship Projects': 'page_49', 'Resume': 'page_7'}
home = included['page_5']['blocks']
for i, b in enumerate(home):
    if b['type'] == 'heading' and b['text'] in homeTargets:
        b['link'] = homeTargets[b['text']]

siteData = {'nav': nav, 'pages': included}
payload = json.dumps(siteData, ensure_ascii=False).replace('</', '<\\/')

payload = payload.replace('https://www.arcgis.com/sharing/rest/content/items/1e8b9cf4f5f445009a3bceabdb94376c/resources/images/', 'images/')
template = open('template.html', encoding='utf-8').read()
open('index.html', 'w', encoding='utf-8').write(template.replace('__SITE_DATA__', payload))

excluded = [p['label'] for p in data['pages'] if p['id'] not in included]
print('included:', len(included), [p['label'] for p in included.values()])
print('excluded:', excluded)
print('size KB:', round(len(payload) / 1024))
