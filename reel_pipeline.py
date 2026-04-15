#!/usr/bin/env python3
"""
Reel Pipeline: YAML台本 → HTML → スクショ → MP4

使い方:
  python3 reel_pipeline.py <script.yaml>

YAMLフォーマット例:
  output: reel_XX_topic.mp4
  color: coral   # yellow(デフォルト) / coral / navy / green / purple
  slides:
    hook:
      marker: 知らないと損！
      main: "退去費用で\\n専門家に頼んだら"
      big_num: "15"
      big_unit: 万円〜
      sub: かかることがある（弁護士費用）
    problem:
      marker: 専門家費用の目安
      main: "頼む前に\\n知ってほしいこと"
      warn: "弁護士：着手金5〜15万円\\n成功報酬：回収額の15〜30%"
      sub: 請求5万円なら費用倒れになる
    solution:
      marker: 自分でできる！ただし
      main: "9割の人が\\n詰まる4つの壁"
      steps:
        - AIの操作方法がわからない
        - 契約書・請求書の読み方
        - 管理会社の返答への対処法
        - 保証会社・代位弁済への対処
      foot: この壁を越えれば費用ゼロで交渉できる
    cta:
      marker: 解決策は2つある
      main: "¥500か\\n¥5,000か"
      sub: "自分でやる→¥500\\n一緒に進む→¥5,000サポート付き"
      btn: ▶ プロフのリンクへ
"""

import glob
import io
import os
import re
import sys
import numpy as np
from PIL import Image

try:
    import yaml
except ImportError:
    os.system(f"{sys.executable} -m pip install pyyaml")
    import yaml

try:
    from moviepy import VideoClip
except ImportError:
    os.system(f"{sys.executable} -m pip install moviepy")
    from moviepy import VideoClip

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    os.system(f"{sys.executable} -m pip install playwright")
    from playwright.sync_api import sync_playwright

# ── 設定 ──────────────────────────────────────────────────────
CHROME_PATH  = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
OUT_W, OUT_H = 1080, 1920
SLIDE_SEC    = 5.0
FPS          = 30
SCALE        = 3   # CSSの360×640px → 1080×1920px

# カラーローテーション順（reel番号に対応）
# reel_01→yellow, reel_02→coral, reel_03→navy, reel_04→green, reel_05→purple, reel_06→yellow ...
COLORS = ['', 'coral', 'navy', 'green', 'purple']  # '' = yellow(デフォルト)


def auto_color(output_path):
    """出力ファイル名の番号からカラーを自動決定。番号がなければ既存MP4数で決定。"""
    m = re.search(r'reel_(\d+)', os.path.basename(output_path))
    if m:
        idx = (int(m.group(1)) - 1) % len(COLORS)
    else:
        existing = len(glob.glob('reel_*.mp4'))
        idx = existing % len(COLORS)
    color = COLORS[idx]
    label = color if color else 'yellow'
    print(f"  カラー自動決定: {label}  (index={idx})")
    return color

# ── CSS（reel_5series.html と同一デザイン）────────────────────
CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Noto Sans JP', sans-serif; background: #fff; }

.slide {
  width: 360px; height: 640px; background: #fff;
  position: relative; overflow: hidden;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
}

/* ── 三角デコレーション ── */
.tri-tl {
  position: absolute; top: 0; left: 0;
  width: 0; height: 0; border-style: solid;
  border-width: 160px 160px 0 0;
  border-color: #FFE040 transparent transparent transparent;
}
.tri-br {
  position: absolute; bottom: 0; right: 0;
  width: 0; height: 0; border-style: solid;
  border-width: 0 0 160px 160px;
  border-color: transparent transparent #FFE040 transparent;
}

/* ── カラーバリエーション ── */
.slide.coral .tri-tl { border-color: #FF6B6B transparent transparent transparent; }
.slide.coral .tri-br { border-color: transparent transparent #FF6B6B transparent; }
.slide.coral .marker  { background: #FF6B6B; color: #fff; }
.slide.coral .step-num { background: #FF6B6B; }
.slide.coral .cta-btn  { background: #FF6B6B; color: #fff; }
.slide.coral .warn-box { border-left: 6px solid #FF6B6B; }
.slide.coral .warn-box p { color: #FF6B6B; }

.slide.navy .tri-tl { border-color: #1E3A5F transparent transparent transparent; }
.slide.navy .tri-br { border-color: transparent transparent #1E3A5F transparent; }
.slide.navy .marker  { background: #1E3A5F; color: #fff; }
.slide.navy .step-num { background: #1E3A5F; color: #FFE040; }
.slide.navy .cta-btn  { background: #1E3A5F; color: #FFE040; }
.slide.navy .warn-box { border-left: 6px solid #1E3A5F; }
.slide.navy .warn-box p { color: #1E3A5F; }

.slide.green .tri-tl { border-color: #2D8C4E transparent transparent transparent; }
.slide.green .tri-br { border-color: transparent transparent #2D8C4E transparent; }
.slide.green .marker  { background: #2D8C4E; color: #fff; }
.slide.green .step-num { background: #2D8C4E; }
.slide.green .cta-btn  { background: #2D8C4E; color: #fff; }
.slide.green .warn-box { border-left: 6px solid #2D8C4E; }
.slide.green .warn-box p { color: #2D8C4E; }

.slide.purple .tri-tl { border-color: #6B46C1 transparent transparent transparent; }
.slide.purple .tri-br { border-color: transparent transparent #6B46C1 transparent; }
.slide.purple .marker  { background: #6B46C1; color: #fff; }
.slide.purple .step-num { background: #6B46C1; }
.slide.purple .cta-btn  { background: #6B46C1; color: #fff; }
.slide.purple .warn-box { border-left: 6px solid #6B46C1; }
.slide.purple .warn-box p { color: #6B46C1; }

/* ── コンテンツ共通 ── */
.content { position: relative; z-index: 10; text-align: center; padding: 0 28px; width: 100%; }

.marker {
  display: inline-block; background: #FFE040;
  padding: 6px 18px; font-size: 19px; font-weight: 700;
  color: #1a1a1a; margin-bottom: 18px; border-radius: 3px;
}
.dots { font-size: 16px; color: #1a1a1a; letter-spacing: 4px; margin-bottom: 8px; display: block; }
.main-text { font-size: 30px; font-weight: 900; color: #1a1a1a; line-height: 1.3; margin-bottom: 20px; }

.big-num {
  font-size: 120px; font-weight: 900; line-height: 1; display: inline-block;
  background: linear-gradient(180deg, #ccc 0%, #888 45%, #444 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
  filter: drop-shadow(3px 3px 0 rgba(0,0,0,0.12));
  letter-spacing: -4px;
}
.big-unit {
  font-size: 48px; font-weight: 900;
  background: linear-gradient(180deg, #bbb 0%, #777 45%, #444 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text; vertical-align: bottom;
}

.warn-box {
  border-left: 6px solid #FFE040; background: #fafafa;
  border-radius: 0 8px 8px 0; padding: 14px 16px; margin: 14px 0; text-align: left;
}
.warn-box p { font-size: 22px; font-weight: 900; color: #B8860B; line-height: 1.4; }
.sub-text { font-size: 17px; font-weight: 700; color: #666; line-height: 1.6; margin-top: 10px; }

.step-list { text-align: left; width: 100%; margin-top: 14px; }
.step-item { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 14px; }
.step-num {
  background: #FFE040; color: #1a1a1a; font-size: 16px; font-weight: 900;
  min-width: 32px; height: 32px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.step-text { font-size: 20px; font-weight: 700; color: #1a1a1a; line-height: 1.4; padding-top: 4px; }
.step-foot { font-size: 15px; font-weight: 700; color: #999; margin-top: 10px; text-align: center; }

.cta-main { font-size: 40px; font-weight: 900; color: #1a1a1a; line-height: 1.25; margin-bottom: 14px; }
.cta-sub  { font-size: 17px; font-weight: 700; color: #555; line-height: 1.7; margin-bottom: 18px; }
.cta-btn  {
  display: inline-block; background: #1a1a1a; color: #FFE040;
  font-size: 18px; font-weight: 900; padding: 10px 28px; border-radius: 40px;
}
"""


# ── HTML生成ヘルパー ───────────────────────────────────────────

def nl2br(text):
    """\\n（文字列or実改行）→ <br>"""
    return str(text).replace('\\n', '<br>').replace('\n', '<br>')


def _slide_hook(s, color):
    return f"""
<div class="slide {color}">
  <div class="tri-tl"></div><div class="tri-br"></div>
  <div class="content">
    <div class="marker">{s['marker']}</div>
    <span class="dots">・・・</span>
    <div class="main-text">{nl2br(s['main'])}</div>
    <div>
      <span class="big-num">{s['big_num']}</span>
      <span class="big-unit">{s['big_unit']}</span>
    </div>
    <div class="sub-text">{nl2br(s['sub'])}</div>
  </div>
</div>"""


def _slide_problem(s, color):
    return f"""
<div class="slide {color}">
  <div class="tri-tl"></div><div class="tri-br"></div>
  <div class="content">
    <div class="marker">{s['marker']}</div>
    <div class="main-text">{nl2br(s['main'])}</div>
    <div class="warn-box"><p>{nl2br(s['warn'])}</p></div>
    <div class="sub-text">{nl2br(s['sub'])}</div>
  </div>
</div>"""


def _slide_solution(s, color):
    steps_html = ''.join(
        f'<div class="step-item">'
        f'<div class="step-num">{i+1}</div>'
        f'<div class="step-text">{step}</div>'
        f'</div>'
        for i, step in enumerate(s['steps'])
    )
    return f"""
<div class="slide {color}">
  <div class="tri-tl"></div><div class="tri-br"></div>
  <div class="content">
    <div class="marker">{s['marker']}</div>
    <div class="main-text">{nl2br(s['main'])}</div>
    <div class="step-list">{steps_html}</div>
    <div class="step-foot">{s['foot']}</div>
  </div>
</div>"""


def _slide_cta(s, color):
    return f"""
<div class="slide {color}">
  <div class="tri-tl"></div><div class="tri-br"></div>
  <div class="content">
    <div class="marker">{s['marker']}</div>
    <div class="cta-main">{nl2br(s['main'])}</div>
    <div class="cta-sub">{nl2br(s['sub'])}</div>
    <div class="cta-btn">{s['btn']}</div>
  </div>
</div>"""


def build_html(config):
    """YAMLコンフィグからHTMLを生成"""
    color = config.get('color')
    if not color:
        color = auto_color(config.get('output', ''))
    else:
        print(f"  カラー手動指定: {color}")
    slides = config['slides']
    body   = (
        _slide_hook(slides['hook'], color) +
        _slide_problem(slides['problem'], color) +
        _slide_solution(slides['solution'], color) +
        _slide_cta(slides['cta'], color)
    )
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@700;900&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>"""


# ── スクショ ─────────────────────────────────────────────────

def screenshot_slides(html_content):
    """HTMLの .slide 要素を順にスクショ → numpy配列リスト"""
    arrays = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=CHROME_PATH,
            args=['--no-sandbox', '--disable-setuid-sandbox'],
        )
        page = browser.new_page(
            viewport={'width': 800, 'height': 4000},
            device_scale_factor=SCALE,
        )
        page.set_content(html_content, wait_until='domcontentloaded')
        try:
            page.wait_for_load_state('networkidle', timeout=8000)
        except Exception:
            page.wait_for_timeout(2000)

        slides = page.query_selector_all('.slide')
        print(f"  スライド検出: {len(slides)}枚")
        for i, slide in enumerate(slides):
            png = slide.screenshot()
            img = Image.open(io.BytesIO(png)).convert('RGB')
            if img.size != (OUT_W, OUT_H):
                img = img.resize((OUT_W, OUT_H), Image.LANCZOS)
            arrays.append(np.array(img).astype('uint8'))
            print(f"  [{i+1}/{len(slides)}] キャプチャ完了  {img.size}")
        browser.close()
    return arrays


# ── MP4生成 ──────────────────────────────────────────────────

def make_mp4(output, frames):
    duration = SLIDE_SEC * len(frames)

    def make_frame(t, _f=frames):
        return _f[min(int(t / SLIDE_SEC), len(_f) - 1)]

    clip = VideoClip(make_frame, duration=duration)
    clip.write_videofile(
        output, fps=FPS, codec='libx264',
        preset='medium', ffmpeg_params=['-crf', '18'],
        logger=None,
    )


# ── キャプション生成 ─────────────────────────────────────────

# 必須ハッシュタグ（RESEARCH_ttkenji_v2.md § 4 準拠）
BASE_HASHTAGS = [
    '退去費用', '原状回復', '賃貸トラブル', '引越し準備',
    '知らないと損', '節約', 'AI活用', '賃貸', '一人暮らし', '敷金',
]

# デュアルCTA（文言固定）
DUAL_CTA = """\
**自分で確認・交渉したい方**
→ https://note.com/ttkenji0232/n/n9d8308b5146e（¥500）

**AIが不慣れ・一緒に進めたい方**
→ https://note.com/ttkenji0232/n/n252503d16f7d（¥5,000サポート付き）"""

# 注意事項（文言固定）
DISCLAIMER = "【注意事項】本記事は情報提供を目的としており、法的助言ではありません。重要な判断については弁護士・消費生活センター等の専門家にご相談ください。"

# 実績・統計数字（必ず使う）
JISSEKI     = "246,488円 → 0円 ＋ 46,950円返金"
STAT_74     = "74%の入居者が国交省ガイドラインを知らないまま全額払っている"
STAT_82     = "交渉した人の82%が減額に成功している"
STAT_6NEN   = "入居6年超の壁紙（クロス）は残存価値ほぼゼロ"
CENTER_TEL  = "188（消費生活センター・全国共通・無料）"


def _clean(text):
    """\\n や <br> を除去してプレーンテキストに"""
    return str(text).replace('\\n', ' ').replace('\n', ' ').replace('<br>', ' ').strip()


def generate_instagram_tiktok_caption(config):
    """Instagram / TikTok 投稿キャプション"""
    s    = config['slides']
    hook = s['hook']
    prob = s['problem']
    sol  = s['solution']

    hook_main = _clean(hook['main'])
    hook_num  = hook.get('big_num', '')
    hook_unit = hook.get('big_unit', '')
    hook_sub  = _clean(hook.get('sub', ''))
    prob_sub  = _clean(prob.get('sub', ''))
    steps     = sol.get('steps', [])
    sol_foot  = _clean(sol.get('foot', ''))
    num_str   = f"{hook_num}{hook_unit}" if hook_num else ''

    points = '\n'.join(f'・{step}' for step in steps[:4])

    caption = f"""\
{hook_main}{f'（{num_str}）' if num_str else ''}

{JISSEKI}

{prob_sub}

{points}

{sol_foot}

▶ 詳しい手順はプロフのリンクから"""

    extra    = config.get('hashtags', [])
    all_tags = list(dict.fromkeys(extra + BASE_HASHTAGS))
    hashtag_line = ' '.join(f'#{t}' for t in all_tags)

    return caption.strip() + '\n\n' + hashtag_line


def generate_youtube_meta(config):
    """YouTube Shorts アップロード用：タイトル＋説明欄"""
    s    = config['slides']
    hook = s['hook']
    prob = s['problem']

    hook_main = _clean(hook['main'])
    hook_num  = hook.get('big_num', '')
    hook_unit = hook.get('big_unit', '')
    prob_main = _clean(prob['main'])
    num_str   = f"{hook_num}{hook_unit}" if hook_num else ''

    # タイトル：[キーワード]+[価値]+[数字]
    if num_str:
        title = f"{hook_main}【{prob_main}・{num_str}】"
    else:
        title = f"{hook_main}【{prob_main}】"

    desc = f"""\
退去費用{JISSEKI}にした方法を解説。

▼詳しい手順・プロンプト全公開
https://note.com/ttkenji0232

▼無料の相談窓口
消費生活センター：{CENTER_TEL}
国民生活センター：https://www.kokusen.go.jp/

---
出典：国土交通省「原状回復をめぐるトラブルとガイドライン（平成23年8月再改訂版）」
https://www.mlit.go.jp/jutakukentiku/house/jutakukentiku_house_tk3_000020.html

#退去費用 #原状回復 #賃貸トラブル #AI活用 #引越し #節約"""

    return f"タイトル：{title}\n\n説明欄：\n{desc}"


def generate_x_post(config):
    """X投稿文（140字以内・3パターン・URLなし）"""
    s     = config['slides']
    hook  = s['hook']
    prob  = s['problem']
    sol   = s['solution']

    hook_main = _clean(hook['main'])
    hook_num  = hook.get('big_num', '')
    hook_unit = hook.get('big_unit', '')
    prob_sub  = _clean(prob.get('sub', ''))
    steps     = sol.get('steps', [])
    sol_foot  = _clean(sol.get('foot', ''))
    num_str   = f"{hook_num}{hook_unit}" if hook_num else ''

    # A. リスト型（保存率高い）
    items = [f'・{step}' for step in steps[:3]] if steps else [f'・{prob_sub}']
    post_a = f"""退去費用で払わなくていいケース：

{chr(10).join(items)}

74%の人が知らずに払っています。
#退去費用 #賃貸トラブル"""

    # B. 問いかけ型（リプ率高い）
    num_part = f"{num_str}、" if num_str else ""
    post_b = f"""{num_part}知ってましたか？

{STAT_82}

まず請求額が正しいか確認してください。
#退去費用 #賃貸"""

    # C. コピペ用型（RT率高い）
    tip = steps[0] if steps else sol_foot
    post_c = f"""退去費用の請求書が届いたら送る一言：

「請求内容の根拠と計算内訳を書面でご提示ください」

これだけで状況が変わることがあります。
#退去費用交渉 #賃貸トラブル"""

    return f"""\
【A. リスト型（保存率高い）】
{post_a}

【B. 問いかけ型（リプ率高い）】
{post_b}

【C. コピペ用型（RT率高い）】
{post_c}"""


def generate_threads_post(config):
    """Threads投稿文（3パターン・導線なし・ハッシュタグあり）"""
    s     = config['slides']
    hook  = s['hook']
    prob  = s['problem']
    sol   = s['solution']

    hook_main = _clean(hook['main'])
    hook_num  = hook.get('big_num', '')
    hook_unit = hook.get('big_unit', '')
    hook_sub  = _clean(hook.get('sub', ''))
    prob_main = _clean(prob['main'])
    prob_sub  = _clean(prob.get('sub', ''))
    sol_foot  = _clean(sol.get('foot', ''))
    steps     = sol.get('steps', [])
    num_str   = f"{hook_num}{hook_unit}" if hook_num else ''

    tags = '#退去費用 #原状回復 #賃貸トラブル #知らないと損 #賃貸 #引越し準備'

    # A. あるあるネタ型
    num_part = f"{num_str}って" if num_str else ""
    post_a = f"""退去費用の請求書に{num_part}書いてあって
「え？」となった人いますか。

知らずに全額払ってた人、けっこういると思います。
74%の人が国交省ガイドラインを知らないらしいです。

{tags}"""

    # B. 質問型
    post_b = f"""退去費用の請求書、{prob_sub if prob_sub else prob_main}

これ、経験したことある人いますか？

{tags}"""

    # C. 語りかけ型
    post_c = f"""知らなくて損した話をします。

退去費用のことなんですが、{sol_foot}

{prob_sub if prob_sub else ''}

{tags}"""

    return f"""\
【A. あるあるネタ型】
{post_a}

【B. 質問型】
{post_b}

【C. 語りかけ型】
{post_c}"""


def generate_note_article(config):
    """note記事（無料・導線）SEO/GEO対策済み"""
    s     = config['slides']
    hook  = s['hook']
    prob  = s['problem']
    sol   = s['solution']

    hook_main = _clean(hook['main'])
    hook_num  = hook.get('big_num', '')
    hook_unit = hook.get('big_unit', '')
    hook_sub  = _clean(hook.get('sub', ''))
    prob_main = _clean(prob['main'])
    prob_warn = _clean(prob.get('warn', ''))
    prob_sub  = _clean(prob.get('sub', ''))
    sol_main  = _clean(sol['main'])
    steps     = sol.get('steps', [])
    sol_foot  = _clean(sol.get('foot', ''))
    num_str   = f"{hook_num}{hook_unit}" if hook_num else ''

    title = f"{hook_main}【{num_str}かかる前に知っておくべきこと】" if num_str else f"{hook_main}【知らないと損する基礎知識】"

    step_lines = '\n'.join(f'- {step}' for step in steps)

    # FAQ（3問）
    faq1_q = f"{hook_main}は絶対に払わないといけないですか？"
    faq1_a = f"いいえ。{STAT_82}。まず請求内容が国交省ガイドラインに沿っているか確認することが重要です。"
    faq2_q = "自分で交渉するのは難しいですか？"
    faq2_a = f"{sol_foot}。AIと国交省ガイドラインを使えば、法律の知識がなくても対応できるケースがあります。"
    faq3_q = "相談できる無料の窓口はありますか？"
    faq3_a = f"消費生活センター（{CENTER_TEL}）に相談できます。年間9万件の賃貸トラブル相談を受け付けています。"

    article = f"""# {title}

{JISSEKI} — これは私の実体験です。{STAT_74}。

国土交通省「原状回復をめぐるトラブルとガイドライン（平成23年8月再改訂版）」では、退去費用の負担ルールが明確に定められています。この記事では「{hook_main}」について、知っておくべきことをまとめます。

---

## {prob_main}とは

{prob_warn if prob_warn else prob_main}

{prob_sub}

{STAT_6NEN}。経年劣化・通常使用による傷は借主負担ではなく大家負担が原則です。

---

## {sol_main}

{sol_foot}

具体的には以下のような壁があります：

{step_lines}

これらの壁を越えるための具体的な手順・プロンプト・テンプレートは、有料記事（¥500）に全部まとめています。

---

## まとめ

- {hook_main}は「払うのが当たり前」ではない
- 国交省ガイドラインで負担ルールが決まっている
- {STAT_82}
- {STAT_6NEN}
- まず請求内容が正しいか確認することが最初の一歩
- 無料相談窓口：消費生活センター {CENTER_TEL}

---

## よくある質問

**Q. {faq1_q}**
A. {faq1_a}

**Q. {faq2_q}**
A. {faq2_a}

**Q. {faq3_q}**
A. {faq3_a}

---

{DUAL_CTA}

---

{DISCLAIMER}

#退去費用 #原状回復 #賃貸トラブル #引越し準備 #知らないと損 #節約 #AI活用 #賃貸 #一人暮らし #敷金
"""
    return article


# ── エントリーポイント ────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("使い方: python3 reel_pipeline.py <script.yaml>")
        sys.exit(1)

    yaml_path = sys.argv[1]
    if not os.path.exists(yaml_path):
        print(f"エラー: {yaml_path} が見つかりません")
        sys.exit(1)

    with open(yaml_path, encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # 出力先を reels/ に自動設定
    out_name = config.get('output', 'reel_output.mp4')
    os.makedirs('reels', exist_ok=True)
    output = os.path.join('reels', os.path.basename(out_name))
    print(f"台本: {yaml_path}")
    print(f"出力: {output}\n")

    print("Step 1: HTML生成")
    html = build_html(config)
    html_path = output.replace('.mp4', '_preview.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  → {html_path}\n")

    print("Step 2: スクショ")
    frames = screenshot_slides(html)

    # スライド画像を個別保存
    base = output.replace('.mp4', '')
    for i, frame in enumerate(frames):
        img_path = f"{base}_slide{i+1:02d}.png"
        Image.fromarray(frame).save(img_path)
        print(f"  → {img_path}")

    print(f"\nStep 3: MP4生成 ({len(frames)}枚 × {SLIDE_SEC}秒)")
    make_mp4(output, frames)
    size_kb = os.path.getsize(output) // 1024
    print(f"  → {output}  ({size_kb} KB)")

    print(f"""
完了 ──────────────────────────────────────────
  動画   : {output}  ({size_kb} KB)
  画像   : {base}_slide01〜04.png
""")


if __name__ == '__main__':
    main()
