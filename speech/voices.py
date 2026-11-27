"""Every VOICEVOX voice, installed or not, from the models' own README table; packs download on request."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

MODELS_VERSION = '0.16.4'  # Same as scripts/install_voicevox.py.
DEFAULT_STYLE = 20  # Mochiko-san, Normal.
# Shown in the app instead of Japanese script (the credit line keeps the official spelling).
CHARACTER_NAMES = {
    '†聖騎士 紅桜†': 'Holy Knight Benizakura', 'あいえるたん': 'Ierutan', 'あんこもん': 'Ankomon', 'ずんだもん': 'Zundamon',
    'ぞん子': 'Zonko', 'ちび式じい': 'Chibishiki-jii', 'もち子さん': 'Mochiko-san', 'ナースロボ＿タイプＴ': 'Nurse Robo Type T',
    'ユーレイちゃん': 'Yurei-chan', '中国うさぎ': 'Chugoku Usagi', '中部つるぎ': 'Chubu Tsurugi', '九州そら': 'Kyushu Sora',
    '冥鳴ひまり': 'Meimei Himari', '剣崎雌雄': 'Kenzaki Mesuo', '四国めたん': 'Shikoku Metan', '夜語トバリ': 'Yogatari Tobari',
    '小夜/SAYO': 'Sayo', '後鬼': 'Goki', '春日部つむぎ': 'Kasukabe Tsumugi', '春歌ナナ': 'Haruka Nana', '暁記ミタマ': 'Akatsuki Mitama',
    '東北きりたん': 'Tohoku Kiritan', '東北ずん子': 'Tohoku Zunko', '東北イタコ': 'Tohoku Itako', '栗田まろん': 'Kurita Maron',
    '櫻歌ミコ': 'Ouka Miko', '波音リツ': 'Namine Ritsu', '満別花丸': 'Manbetsu Hanamaru', '猫使アル': 'Nekotsuka Aru',
    '猫使ビィ': 'Nekotsuka Bi', '玄野武宏': 'Kurono Takehiro', '琴詠ニア': 'Kotoyomi Nia', '白上虎太郎': 'Shirakami Kotaro',
    '里石ユカ': 'Satoishi Yuka', '雀松朱司': 'Wakamatsu Akashi', '離途': 'Rito', '雨晴はう': 'Amehare Hau', '青山龍星': 'Aoyama Ryusei',
    '麒ヶ島宗麟': 'Kigashima Sorin', '黒沢冴白': 'Kurosawa Saehaku'}
STYLE_NAMES = {
    'あまあま': 'Sweet', 'うきうき': 'Cheerful', 'おこ': 'Annoyed', 'おちつき': 'Calm', 'おどおど': 'Timid', 'おどろき': 'Surprised',
    'かなしい': 'Sad', 'かなしみ': 'Sad', 'けだるげ': 'Languid', 'こわがり': 'Scared', 'ささやき': 'Whisper', 'しっとり': 'Soft',
    'たのしい': 'Happy', 'つぼみ': 'Bud', 'つよつよ': 'Strong', 'なみだめ': 'Teary', 'ぬいぐるみver.': 'Plush toy', 'のんびり': 'Relaxed',
    'びえーん': 'Wailing', 'びくびく': 'Nervous', 'ふつう': 'Normal', 'ぶりっ子': 'Cutesy', 'へろへろ': 'Worn out', 'よわよわ': 'Weak',
    'わーい': 'Excited', 'アナウンス': 'Announcer', 'クイーン': 'Queen', 'シリアス': 'Serious', 'セクシー': 'Sultry',
    'セクシー／あん子': 'Sultry (Anko)', 'ツクモちゃん': 'Tsukumo-chan', 'ツンギレ': 'Snappy', 'ツンツン': 'Prickly', 'ノーマル': 'Normal',
    'ヒソヒソ': 'Hushed', 'ヘロヘロ': 'Worn out', 'ボーイ': 'Boy', 'ロリ': 'Young', '不機嫌': 'Grumpy', '人見知り': 'Shy',
    '人間ver.': 'Human', '人間（怒り）ver.': 'Human (angry)', '低血圧': 'Sleepy', '元気': 'Energetic', '内緒話': 'Secret',
    '呆れ': 'Exasperated', '哀しみ': 'Sorrowful', '喜び': 'Joyful', '囁き': 'Whisper', '実況風': 'Commentator', '怒り': 'Angry',
    '恐怖': 'Afraid', '悲しみ': 'Sad', '明るい': 'Bright', '楽々': 'Easygoing', '泣き': 'Crying', '熱血': 'Fiery', '甘々': 'Sweet',
    '第二形態': 'Second form', '絶望と敗北': 'Defeated', '覚醒': 'Awakened', '読み聞かせ': 'Storyteller', '鬼ver.': 'Oni'}
SAMPLE = 'こんにちは。これからこの声でお話しするね。'
CREDIT_NAMES = {'もち子さん': 'もち子(cv 明日葉よもぎ)'}  # Credit spelling the character's terms ask for.


def catalog(root):
    """[{pack, character, style, id, installed}] in the README's order."""
    root = Path(root)
    try: text = (root / 'models/README.txt').read_text(encoding='utf-8')
    except OSError: return []
    rows = re.findall(r'^\| (\d+\.vvm) \| ([^|]+?) \| ([^|]+?) \| (\d+) \|$', text, re.M)
    return [{'pack': pack, 'character': character, 'style': style, 'id': int(style_id),
             'name': CHARACTER_NAMES.get(character, character), 'style_name': STYLE_NAMES.get(style, style),
             'installed': (root / 'models/vvms' / pack).is_file()} for pack, character, style, style_id in rows]


def voice(root, style_id):
    return next((v for v in catalog(root) if v['id'] == style_id), None)


def credit(character):
    return 'VOICEVOX:' + CREDIT_NAMES.get(character, character)


TERMS_EN = """Unofficial English translation. The Japanese terms (models/TERMS.txt) are the binding text.

VOICEVOX voice model terms
Allowed:
1. Use for commercial or non-commercial purposes.
2. Bundle into an application and redistribute it.
3. When you use the generated speech, follow the terms of each voice library (below).
4. When you let others use the generated speech, require them to follow points 3 and 4.
Not allowed:
- Decompiling or reverse engineering, or publishing how to do so.
- Anything that harms the creators or third parties.
- Anything against public order and morals.
Disclaimer: the creators are not responsible for any damage or loss caused by this software.
Other: a credit showing that VOICEVOX was used is required.

Voice library terms (each character's own terms apply; read them before use):"""


def terms_en(root):
    """English terms: translated general part, then each character's required credit and terms link."""
    try: text = (Path(root) / 'models/TERMS.txt').read_text(encoding='utf-8')
    except OSError: return ''
    lines = [TERMS_EN]
    for character, body in re.findall(r'^## (.+?)\n(.*?)(?=^## |\Z)', text.split('# 音声ライブラリ利用規約', 1)[-1], re.M | re.S):
        credits = re.findall(r'「(VOICEVOX:[^」]+)」', body)
        url = re.search(r'https?://\S+', body)
        lines.append(f'- {CHARACTER_NAMES.get(character.strip(), character.strip())}: credit "{credits[0] if credits else credit(character.strip())}"'
                     + (f'; terms: {url[0]}' if url else ''))
    return '\n'.join(lines)


def pack_sizes():
    """Exact download size of each pack from the VOICEVOX release assets (never hardcoded)."""
    url = f'https://api.github.com/repos/VOICEVOX/voicevox_vvm/releases/tags/{MODELS_VERSION}'
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'chassie'}), timeout=20) as response:
        return {a['name']: a['size'] for a in json.load(response).get('assets', []) if a['name'].endswith('.vvm')}


def download(root, pack):
    """Run the official downloader into a scratch folder, then move only that pack in place."""
    root = Path(root)
    if not re.fullmatch(r'\d{1,3}\.vvm', str(pack)): raise ValueError('Unknown voice pack')
    with tempfile.TemporaryDirectory(dir=root) as scratch:
        subprocess.run([str(root / 'download'), '--only', 'models', '--models-pattern', pack, '--models-version', MODELS_VERSION,
                        '--output', scratch], input='y\n', text=True, capture_output=True, timeout=1800, check=True,
                       env={**os.environ, 'COLUMNS': '120', 'LINES': '40'})
        shutil.move(Path(scratch) / 'models/vvms' / pack, root / 'models/vvms' / pack)
    # ponytail: a failed download starts over next time; resume needs the tool to support it.
