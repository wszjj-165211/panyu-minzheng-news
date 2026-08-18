# -*- coding: utf-8 -*-
"""
GitHub Actions 全自动抓取脚本
=============================
抓取 3 个官方源 → 自动摘要/分类 → 合并进 news_data.json
全程无需人工，供 GitHub Actions 每日定时运行。

运行: python scripts/fetch_all.py [--pages N]
"""
import json, re, ssl, sys, os, urllib.request, datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE, 'data', 'news_data.json')

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

HDR = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}

def get(url, timeout=20, referer=None):
    h = dict(HDR)
    if referer:
        h['Referer'] = referer
    req = urllib.request.Request(url, headers=h)
    return urllib.request.urlopen(req, timeout=timeout, context=CTX).read().decode('utf-8', 'ignore')

def dedup_key(link):
    m = re.search(r'(article-\d+|post_\d+)', link)
    return m.group(1) if m else link.split('#')[0]

YEAR_START = '2026-01-01'
def in_scope(date):
    return bool(date) and date >= YEAR_START

# ================= 源1: 番禺区慈善会官网 =================
PYCS_COLS = [(2337, '媒体报道'), (2338, '机构资讯'), (2498, '系列报道'), (2501, '公示公告'), (2495, '党建要闻'), (2499, '月报')]

def fetch_pycs():
    out = []
    for col, cname in PYCS_COLS:
        try:
            h = get('http://www.pycs.org.cn/list-%d-1-20.html' % col)
        except Exception:
            continue
        for b in re.split(r'<li', h):
            m = re.search(r'href="(/article-(\d+)\.html)"[^>]*>([^<]{4,100})</a>', b)
            if not m:
                continue
            dm = re.search(r'(\d{4})-(\d{2})-(\d{2})', b)
            date = dm.group(0) if dm else ''
            if not in_scope(date):
                continue
            out.append({'date': date, 'title': re.sub(r'\s+', ' ', m.group(3)).strip(),
                        'link': 'https://www.pycs.org.cn' + m.group(1), 'source': '番禺区慈善会官网', 'col': cname})
    return out

# ================= 源2: 广州市民政局 =================
def fetch_mzj():
    out = []
    for page in (1, 2):
        url = 'http://mzj.gz.gov.cn/dt/mzdt/index.html' if page == 1 else 'http://mzj.gz.gov.cn/dt/mzdt/index_2.html'
        try:
            h = get(url)
        except Exception:
            continue
        for b in re.split(r'<li', h):
            m = re.search(r'href="([^"]*content/post_(\d+)\.html)"[^>]*>([^<]{4,100})</a>', b)
            if not m:
                continue
            title = re.sub(r'\s+', ' ', m.group(3)).strip()
            if '番禺' not in title:
                continue
            dm = re.search(r'(\d{4})-(\d{2})-(\d{2})', b)
            date = dm.group(0) if dm else ''
            if date and not in_scope(date):
                continue
            link = m.group(1)
            if not link.startswith('http'):
                link = 'http://mzj.gz.gov.cn' + link
            out.append({'date': date, 'title': title, 'link': link, 'source': '广州市民政局官网', 'col': '市民政局动态'})
    return out

# ================= 源3: 番禺区政府网（部门动态+16镇街） =================
BASE_PY = 'https://www.panyu.gov.cn'
COLUMNS = [
    ('部门动态', 'zwgk/zfxxgkml/xxgkml/zwdt/bmdt'),
    ('沙湾镇政府', 'zwgk/zfxxgkml/xxgkml/zwdt/zjxx/swzzf'),
    ('石碁镇政府', 'zwgk/zfxxgkml/xxgkml/zwdt/zjxx/s127zzf'),
    ('新造镇政府', 'zwgk/zfxxgkml/xxgkml/zwdt/zjxx/xzzzf'),
    ('南村镇政府', 'zwgk/zfxxgkml/xxgkml/zwdt/zjxx/nczzf'),
    ('化龙镇政府', 'zwgk/zfxxgkml/xxgkml/zwdt/zjxx/hlzzf'),
    ('石楼镇政府', 'zwgk/zfxxgkml/xxgkml/zwdt/zjxx/slzzf'),
    ('市桥街道办事处', 'zwgk/zfxxgkml/xxgkml/zwdt/zjxx/sqjdbsc'),
    ('沙头街道办事处', 'zwgk/zfxxgkml/xxgkml/zwdt/zjxx/stjdbsc'),
    ('东环街道办事处', 'zwgk/zfxxgkml/xxgkml/zwdt/zjxx/dhjdbsc'),
    ('桥南街道办事处', 'zwgk/zfxxgkml/xxgkml/zwdt/zjxx/qnjdbsc'),
    ('小谷围街道办事处', 'zwgk/zfxxgkml/xxgkml/zwdt/zjxx/xgwjdbsc'),
    ('大石街道办事处', 'zwgk/zfxxgkml/xxgkml/zwdt/zjxx/dsjdbsc'),
    ('洛浦街道办事处', 'zwgk/zfxxgkml/xxgkml/zwdt/zjxx/lpjdbsc'),
    ('钟村街道办事处', 'zwgk/zfxxgkml/xxgkml/zwdt/zjxx/zcjdbsc'),
    ('石壁街道办事处', 'zwgk/zfxxgkml/xxgkml/zwdt/zjxx/sbjdbsc'),
    ('大龙街道办事处', 'zwgk/zfxxgkml/xxgkml/zwdt/zjxx/dljdbsc'),
]
CAT_RULES = [
    (['婚姻', '婚俗', '结婚', '离婚', '登记处', '甜蜜经济'], '婚姻登记'),
    (['养老', '长者', '颐康', '银发', '老年', '敬老', '饭堂', '助餐', '适老化', '居家养老', '养老服务'], '养老服务'),
    (['儿童', '未成年人', '青少年', '亲子', '托育', '六一', '困境儿童', '护苗', '助学', '托管班', '少儿'], '未成年人保护'),
    (['救助', '低保', '特困', '残疾人', '残疾', '帮扶', '慰问', '微心愿'], '社会救助'),
    (['慈善', '爱心', '捐赠', '义卖', '募捐', '公益慈善', '善款'], '社区慈善'),
    (['社工', '志愿', '志愿者'], '社会组织'),
    (['社会组织', '社团', '协会', '商会', '联合会'], '社会组织'),
    (['殡葬', '墓园', '祭扫'], '殡葬管理'),
    (['区划', '地名', '界桩'], '区划地名'),
    (['社区治理', '居委会', '村委会', '基层', '网格', '议事', '居民自治'], '基层治理'),
]
KEYWORDS = sorted({kw for rules in CAT_RULES for kw in rules[0]}, key=len, reverse=True)

def parse_list(html):
    items = []
    m = re.search(r'news_list[\s\S]*?</ul>', html)
    if not m:
        return items
    for li in re.findall(r'<li[^>]*>([\s\S]*?)</li>', m.group(0)):
        am = re.search(r"<a[^>]+href='([^']+)'[^>]*title='([^']*)'", li) or re.search(r'<a[^>]+href="([^"]+)"[^>]*title="([^"]*)"', li)
        if not am:
            continue
        link, title = am.group(1), am.group(2).strip()
        dm = re.search(r'<span[^>]*>\s*([\d-]+)', li)
        date = dm.group(1).strip() if dm else ''
        if link.startswith('/'):
            link = BASE_PY + link
        items.append({'title': title, 'link': link, 'date': date})
    return items

def fetch_content(link):
    try:
        body = get(link, timeout=20, referer=BASE_PY + '/')
        m = re.search(r'id="zoomcon"([\s\S]*?)</div>', body)
        seg = m.group(1) if m else ''
        txt = re.sub(r'<[^>]+>', ' ', seg)
        import html as h
        return h.unescape(re.sub(r'\s+', ' ', txt)).strip()
    except Exception:
        return ''

def make_summary(text, maxlen=200):
    t = text.strip().lstrip('> ').strip()
    return (t[:maxlen] + ('…' if len(t) > maxlen else '')) if t else ''

def classify(title, text):
    cat = '其他民政业务'
    labels = []
    for kws, c in CAT_RULES:
        if any(k in title for k in kws):
            cat = c
            break
    blob = title + text[:200]
    if cat == '养老服务':
        labels.append('养老服务')
        if '银发' in blob:
            labels.append('银发经济')
    elif cat == '社区慈善':
        labels.append('社区慈善')
        if '志愿' in blob:
            labels.append('志愿服务')
    elif cat == '未成年人保护':
        labels.append('未成年人保护')
        if any(k in title for k in ['儿童', '亲子', '六一']):
            labels.append('儿童')
        if '青少年' in title:
            labels.append('未成年人')
    elif cat == '婚姻登记':
        labels.append('婚姻登记')
        if '婚俗' in title or '家庭辅导' in blob:
            labels.append('婚俗改革')
    elif cat == '社会救助':
        labels.append('社会救助')
        if '残疾' in title:
            labels.append('残疾人')
    elif cat == '社会组织':
        labels.append('社工' if '社工' in title else '社会组织')
    elif cat == '基层治理':
        labels.append('基层治理')
    if not labels:
        labels.append(cat)
    return cat, list(dict.fromkeys(labels))

def fetch_panyu(max_pages=2):
    records = []
    seen = set()
    for name, path in COLUMNS:
        for page in range(1, max_pages + 1):
            p = 'index.html' if page == 1 else f'index_{page}.html'
            try:
                items = parse_list(get(f'{BASE_PY}/{path}/{p}', referer=BASE_PY + '/'))
            except Exception:
                break
            if not items:
                break
            for it in items:
                if it['link'] in seen or not any(k in it['title'] for k in KEYWORDS):
                    continue
                if it['date'] and not in_scope(it['date']):
                    continue
                seen.add(it['link'])
                text = fetch_content(it['link'])
                cat, labels = classify(it['title'], text)
                records.append({
                    'date': it['date'] or '', 'title': it['title'],
                    'link': it['link'], 'source': '番禺区人民政府门户网站',
                    'col': name, 'category': cat, 'labels': labels,
                    'summary': make_summary(text),
                })
            if items[-1]['date'] and items[-1]['date'] < '2026-01-01':
                break
    return records

# ================= 合并入库 =================
def merge(records, tag):
    d = json.load(open(DATA_PATH, encoding='utf-8'))
    existing = {dedup_key(r['link']) for r in d['records']}
    added = 0
    for it in records:
        k = dedup_key(it['link'])
        if k in existing:
            continue
        existing.add(k)
        d['records'].append({
            'date': it['date'], 'title': it['title'], 'source': it['source'],
            'link': it['link'], 'category': it['category'], 'extra_cats': [],
            'labels': it['labels'], 'summary': it['summary'],
            'note': f'【{tag}自动抓取】{it.get("col", "")}',
        })
        added += 1
    d['meta']['total'] = len(d['records'])
    d['meta']['updated_at'] = datetime.datetime.now().strftime('%Y-%m-%d')
    d['meta']['generated_at'] = datetime.datetime.now().strftime('%Y-%m-%d')
    json.dump(d, open(DATA_PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return added

def main():
    max_pages = 2
    if '--pages' in sys.argv:
        try:
            max_pages = int(sys.argv[sys.argv.index('--pages') + 1])
        except Exception:
            pass
    print('=' * 56)
    print('全自动抓取  ', datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
    print('=' * 56)
    total_added = 0
    total_added += merge(fetch_pycs(), '慈善会官网')
    total_added += merge(fetch_mzj(), '市民政局')
    total_added += merge(fetch_panyu(max_pages), '区政府网')
    print('合计新增:', total_added)
    d = json.load(open(DATA_PATH, encoding='utf-8'))
    print('当前总量:', d['meta']['total'])
    return 0

if __name__ == '__main__':
    sys.exit(main())
