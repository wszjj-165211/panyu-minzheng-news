#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
════════════════════════════════════════════════════════════════
  番禺区民政新闻助手 · 一键构建脚本（整个系统唯一需要跑的代码）
════════════════════════════════════════════════════════════════

  这一个文件 = 原来的 fetch_all.py（抓取） + build.py（打包） 合并版

  它自动做两件事：
    第 1 步【抓取】 去 5 个官方源网站，把当天的新新闻抓回来，
                     存进  data/news_data.json（新闻库）
    第 2 步【打包】 把新闻库塞进 index.template.html（页面模板），
                     生成 index.html（真正对外发布的网页）

  什么时候用？
    · 平时【什么都不用做】——GitHub Actions 每天早上 10:30 自动运行本文件
    · 想立刻手动更新：去 GitHub 仓库 → Actions → daily-fetch → Run workflow
    · 想在电脑上试跑：   python run_all.py

  用法：
    python run_all.py            # 默认抓取（一般够用）
    python run_all.py --pages 3  # 抓更深一点（不常用）
"""
import json, re, ssl, sys, os, gzip, urllib.request, urllib.parse, datetime

# 本文件在仓库根目录，所以数据/模板都在它旁边的文件夹里
BASE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE, 'data', 'news_data.json')
TPL_PATH = os.path.join(BASE, 'index.template.html')
OUT_PATH = os.path.join(BASE, 'index.html')

# 只保留 2026 年以后的新闻（太旧的不收）
YEAR_START = '2026-01-01'

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

HDR = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}

# ═══════════════════════════════════════════════════════════════
#  第 1 部分：抓取（以下内容一般不需要改，除非官网改版）
# ═══════════════════════════════════════════════════════════════

def get(url, timeout=20, referer=None):
    h = dict(HDR)
    if referer:
        h['Referer'] = referer
    req = urllib.request.Request(url, headers=h)
    resp = urllib.request.urlopen(req, timeout=timeout, context=CTX)
    raw = resp.read()
    if resp.headers.get('Content-Encoding') == 'gzip':
        raw = gzip.decompress(raw)
    return raw.decode('utf-8', 'ignore')

def dedup_key(link):
    """从链接里提取文章编号，用来判断一条新闻是不是已经收过了"""
    m = re.search(r'(article-\d+|post_\d+|c\d{6,})', link)
    if m:
        return m.group(1)
    seg = link.rstrip('/').split('/')[-1].split('.')[0]
    return seg if seg else link.split('#')[0]

def in_scope(date):
    return bool(date) and date >= YEAR_START

# 业务分类规则：标题里出现这些词 → 归到对应分类（想调整分类就改这里）
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

# ---------- 源 1：番禺区慈善会官网 ----------
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
            title = re.sub(r'\s+', ' ', m.group(3)).strip()
            cat, labels = classify(title, '')
            out.append({'date': date, 'title': title,
                        'link': 'https://www.pycs.org.cn' + m.group(1), 'source': '番禺区慈善会官网',
                        'col': cname, 'category': cat, 'labels': labels, 'summary': ''})
    return out

# ---------- 源 2：广州市民政局（只收标题带"番禺"的） ----------
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
            cat, labels = classify(title, '')
            out.append({'date': date, 'title': title, 'link': link, 'source': '广州市民政局官网',
                        'col': '市民政局动态', 'category': cat, 'labels': labels, 'summary': ''})
    return out

# ---------- 源 3：番禺区政府网（部门动态 + 16 个镇街） ----------
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
            if items[-1]['date'] and items[-1]['date'] < YEAR_START:
                break
    return records

# ---------- 源 4：南方+ 番禺频道 ----------
NFAPP_COLUMN = 24957

def norm_date(v):
    """发布时间可能是 '2026-08-17 10:00'、'2026-08-17T10:00' 或毫秒时间戳，统一转成 日期"""
    if isinstance(v, (int, float)):
        ts = v / 1000 if v > 1e12 else v
        return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
    s = str(v or '').strip()
    m = re.search(r'(\d{4}-\d{2}-\d{2})', s)
    return m.group(1) if m else ''

def fetch_nfnews(max_pages=2):
    out = []
    for page in range(1, max_pages + 1):
        url = ('https://api.nfapp.southcn.com/nfplus-manuscript-web/article/list'
               '?columnId=%d&nfhSubCount=1&pageNum=%d&pageSize=20' % (NFAPP_COLUMN, page))
        try:
            data = json.loads(get(url, referer='https://m.nfapp.southcn.com/'))
        except Exception:
            continue
        lst = (data.get('data') or {}).get('list') or []
        if not lst:
            break
        for a in lst:
            title = re.sub(r'<[^>]+>', '', a.get('title') or '').strip()
            date = norm_date(a.get('releaseTime'))
            if not title or not in_scope(date):
                continue
            if not any(k in title for k in KEYWORDS):
                continue
            aid = str(a.get('articleId') or '')
            ymd = re.sub(r'[^\d]', '', str(a.get('releaseTime') or ''))[:8]
            if len(ymd) == 8 and aid:
                link = 'https://static.nfnews.com/content/%s/%s/c%s.html' % (ymd[:6], ymd[6:], aid)
            else:
                link = a.get('shareUrl') or ''
            if not link:
                continue
            cat, labels = classify(title, '')
            out.append({'date': date, 'title': title, 'link': link,
                        'source': '南方+', 'col': '南方+番禺频道',
                        'category': cat, 'labels': labels, 'summary': ''})
    return out

# ---------- 源 5：新花城 番禺频道 ----------
HC_SITE = '5e88c884e2ed4e7a9a8d5225c299f707'
HC_CHANNEL = '1253f926cf4c4f27b961b7761bb6f672'
HC_KWS = ['养老', '慈善', '捐赠', '儿童', '救助', '低保', '婚姻', '社工', '志愿', '社区治理', '残疾', '殡葬']

def fetch_huacheng(max_pages=3):
    out = []
    for kw in HC_KWS:
        for page in range(1, max_pages + 1):
            url = ('https://www.gz-cmc.com/contentapi/api/content/getChannelAllContents'
                   '?siteId=%s&channelId=%s&currentTimeMillis=%d&keyword=%s&pageNum=%d&pageSize=20'
                   % (HC_SITE, HC_CHANNEL, int(datetime.datetime.now().timestamp() * 1000),
                      urllib.parse.quote(kw), page))
            try:
                data = json.loads(get(url, referer='https://www.gz-cmc.com/'))
            except Exception:
                continue
            lst = data.get('list') or []
            if not lst:
                break
            for it in lst:
                a = it.get('data') or it
                title = re.sub(r'<[^>]+>', '', a.get('title') or '').strip()
                date = norm_date(a.get('publishTime'))
                link = a.get('url') or ''
                if not title or not link or not in_scope(date):
                    continue
                if not any(k in title for k in KEYWORDS):
                    continue
                cat, labels = classify(title, '')
                out.append({'date': date, 'title': title, 'link': link,
                            'source': '新花城', 'col': '新花城番禺频道',
                            'category': cat, 'labels': labels, 'summary': ''})
    return out

def merge(records, tag):
    """把抓回来的新新闻合并进新闻库（自动去重、无链接不收）"""
    d = json.load(open(DATA_PATH, encoding='utf-8'))
    existing = {dedup_key(r['link']) for r in d['records']}
    added = 0
    for it in records:
        link = it.get('link') or ''
        if not link.startswith('http'):
            continue
        k = dedup_key(link)
        if k in existing:
            continue
        existing.add(k)
        cat = it.get('category') or '其他民政业务'
        d['records'].append({
            'date': it['date'], 'title': it['title'], 'source': it['source'],
            'link': link, 'category': cat, 'extra_cats': [],
            'labels': it.get('labels') or [cat], 'summary': it.get('summary', ''),
            'note': f'【{tag}自动抓取】{it.get("col", "")}',
        })
        added += 1
    d['meta']['total'] = len(d['records'])
    d['meta']['updated_at'] = datetime.datetime.now().strftime('%Y-%m-%d')
    d['meta']['generated_at'] = datetime.datetime.now().strftime('%Y-%m-%d')
    json.dump(d, open(DATA_PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return added

# ═══════════════════════════════════════════════════════════════
#  第 2 部分：打包（把数据塞进模板，生成对外发布的 index.html）
# ═══════════════════════════════════════════════════════════════

# 分类配色兜底：万一数据里缺了配色，就用下面这套（想换颜色改这里）
DEFAULT_CAT_COLORS = {
    "社区慈善":     {"bg": "#FDE9DD", "text": "#C2551A"},
    "养老服务":     {"bg": "#FBF0D9", "text": "#B07A1A"},
    "婚姻登记":     {"bg": "#E9F4E4", "text": "#3E7C22"},
    "未成年人保护": {"bg": "#E3EFFC", "text": "#1E66B0"},
    "社会救助":     {"bg": "#ECECEF", "text": "#5A5A66"},
    "基层治理":     {"bg": "#EDE5F9", "text": "#6B3FA0"},
    "社会组织":     {"bg": "#E4E9F7", "text": "#3D54A8"},
    "殡葬管理":     {"bg": "#E6EBEE", "text": "#4E6A7C"},
    "区划地名":     {"bg": "#FCE8E2", "text": "#B05A30"},
    "其他民政业务": {"bg": "#EFEFEA", "text": "#6E6E63"},
}

def ensure_meta(data):
    """数据自愈：缺 cat_colors 等关键字段时自动补上（防止页面打开崩溃）"""
    fixed = False
    meta = data.get('meta')
    if not isinstance(meta, dict):
        meta = {}
        data['meta'] = meta
        fixed = True
    if not isinstance(meta.get('cat_colors'), dict) or not meta['cat_colors']:
        meta['cat_colors'] = DEFAULT_CAT_COLORS
        fixed = True
    if not meta.get('dimensions'):
        meta['dimensions'] = list(DEFAULT_CAT_COLORS.keys())
        fixed = True
    if not meta.get('total') and data.get('records'):
        meta['total'] = len(data['records'])
        fixed = True
    return fixed

def build_page():
    """第 2 步：读模板 → 把数据内嵌进去 → 生成 index.html"""
    if not os.path.exists(DATA_PATH):
        print('ERROR: 缺少数据文件 %s' % DATA_PATH)
        sys.exit(1)
    with open(DATA_PATH, encoding='utf-8') as f:
        data = json.load(f)
    records = data.get('records') or []
    if not records:
        print('ERROR: 数据为空，拒绝生成页面（防止把空数据发布上线）')
        sys.exit(1)
    # 自洁：没有有效链接的条目不放进页面（点不开的新闻不收）
    before = len(records)
    records = [r for r in records if (r.get('link') or '').startswith('http')]
    if len(records) != before:
        print('注意: 已剔除 %d 条无有效链接条目' % (before - len(records)))
        data['records'] = records
        data['meta']['total'] = len(records)
    if ensure_meta(data):
        print('自愈: meta 缺失字段已用默认补齐 (cat_colors/dimensions/total)')
    payload = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    with open(TPL_PATH, encoding='utf-8') as f:
        tpl = f.read()
    marker = '/*__DATA__*/null'
    if marker not in tpl:
        print('ERROR: 模板中未找到占位符 %r' % marker)
        sys.exit(1)
    html = tpl.replace(marker, '/*__DATA__*/' + payload)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        f.write(html)
    total = data.get('meta', {}).get('total', len(data.get('records', [])))
    print('OK: index.html 已生成 | 内嵌数据 %d 条 | %.1f KB' % (total, os.path.getsize(OUT_PATH) / 1024))

# ═══════════════════════════════════════════════════════════════
#  主程序：第 1 步抓取 → 第 2 步打包
# ═══════════════════════════════════════════════════════════════

def main():
    max_pages = 2
    if '--pages' in sys.argv:
        try:
            max_pages = int(sys.argv[sys.argv.index('--pages') + 1])
        except Exception:
            pass
    print('=' * 56)
    print('一键构建   ', datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
    print('=' * 56)
    print('第 1 步：抓取 5 个官方源...')
    total_added = 0
    total_added += merge(fetch_pycs(), '慈善会官网')
    total_added += merge(fetch_mzj(), '市民政局')
    total_added += merge(fetch_panyu(max_pages), '区政府网')
    total_added += merge(fetch_nfnews(5), '南方+')
    total_added += merge(fetch_huacheng(2), '新花城')
    print('本次新增:', total_added, '条')
    print('第 2 步：打包生成 index.html...')
    build_page()
    return 0

if __name__ == '__main__':
    sys.exit(main())
