# -*- coding: utf-8 -*-
"""
构建脚本：把 data/news_data.json 内嵌进 index.html
====================================================================
解决 GitHub Pages 在国内手机网络下加载外部 JSON 不稳定导致的
「数据加载失败」问题 —— 页面自带数据，打开即用、永不失联。

用法: python scripts/build.py
输入: index.template.html（含 /*__DATA__*/null 占位符）+ data/news_data.json
输出: index.html（内嵌全部数据，可直接部署）

日常抓取流程: fetch_all.py 更新数据 → build.py 重新生成 index.html → git commit
"""
import json, os, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(BASE, 'index.template.html')
DATA = os.path.join(BASE, 'data', 'news_data.json')
OUT = os.path.join(BASE, 'index.html')


def main():
    if not os.path.exists(DATA):
        print('ERROR: 缺少 %s' % DATA)
        sys.exit(1)
    with open(DATA, encoding='utf-8') as f:
        data = json.load(f)
    records = data.get('records') or []
    if not records:
        print('ERROR: 数据为空，拒绝生成页面（防止把空数据发布上线）')
        sys.exit(1)
    # 自洁：无有效链接的条目不内嵌（跳转不了的不展示）
    before = len(records)
    records = [r for r in records if (r.get('link') or '').startswith('http')]
    if len(records) != before:
        print('注意: 已剔除 %d 条无有效链接条目' % (before - len(records)))
        data['records'] = records
        data['meta']['total'] = len(records)
    # 转义 </ 防止 </script> 提前闭合 HTML；JSON 字符串里 \/ 是合法转义
    payload = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    with open(TPL, encoding='utf-8') as f:
        tpl = f.read()
    marker = '/*__DATA__*/null'
    if marker not in tpl:
        print('ERROR: 模板中未找到占位符 %r' % marker)
        sys.exit(1)
    html = tpl.replace(marker, '/*__DATA__*/' + payload)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(html)
    total = data.get('meta', {}).get('total', len(data.get('records', [])))
    print('OK: index.html 已生成 | 内嵌数据 %d 条 | %.1f KB' % (total, os.path.getsize(OUT) / 1024))


if __name__ == '__main__':
    main()
