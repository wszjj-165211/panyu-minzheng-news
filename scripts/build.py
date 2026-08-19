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

# 分类配色兜底：若数据 meta 缺失 cat_colors（防止合并/抓取脚本丢失字段），构建时自动补齐
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
    """数据自愈：确保 meta 必备字段齐全，缺失即用默认补齐（返回是否修复）"""
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
    # 自愈：补齐缺失的 meta 字段（cat_colors 等），防止页面初始化崩溃
    if ensure_meta(data):
        print('自愈: meta 缺失字段已用默认补齐 (cat_colors/dimensions/total)')
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
