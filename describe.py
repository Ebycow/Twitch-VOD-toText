#!/usr/bin/env python3
"""
describe.py - キャプチャ画像を VLM で説明してタイムライン付きテキストに保存する
使用方法: python3 describe.py <VOD_ID>
出力:     describes/<VOD_ID>.txt

describes ファイルのフォーマット:
    [HH:MM:SS]
    説明テキスト（複数行可）

    [HH:MM:SS]
    次の説明テキスト
    ...
"""
import base64
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent
CAPTURES_DIR = SCRIPT_DIR / "captures"
DESCRIBES_DIR = SCRIPT_DIR / "describes"
TRANSCRIPTIONS_DIR = SCRIPT_DIR / "transcriptions"

# 画像の前後何秒の発話をコンテキストとして使うか
TRANSCRIPT_WINDOW = 60  # 秒

load_dotenv(SCRIPT_DIR / ".env")

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
VISION_MODEL = os.environ.get("VISION_MODEL", "google/gemini-3.1-flash-lite-preview")

PROMPT = """\
この画像はTwitch配信のスクリーンショットです。
配信画面を見ていない人にも伝わるような文章で詳細に、映っている内容を日本語で説明してください。
興味深い部分やおかしな点、異常な部分を説明に含めます。
撮影日時が未来であることには一切触れてはいけません。
出力はmarkdownなどの構造的な文章には絶対にせず、プレーンな文章にしてください。
"""


def parse_srt(filepath: Path) -> list[tuple[int, str]]:
    """SRT ファイルをパースして (秒数, テキスト) のリストを返す"""
    import re
    entries = []
    content = filepath.read_text(encoding="utf-8", errors="replace")
    for block in re.split(r"\n\n+", content.strip()):
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        m = re.match(r"(\d{2}):(\d{2}):(\d{2}),\d+", lines[1])
        if not m:
            continue
        sec = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        text = " ".join(lines[2:]).strip()
        entries.append((sec, text))
    return entries


def get_context_transcript(srt_entries: list[tuple[int, str]], center_sec: int) -> str:
    """center_sec の前後 TRANSCRIPT_WINDOW 秒以内の発話を結合して返す"""
    start = center_sec - TRANSCRIPT_WINDOW
    end = center_sec + TRANSCRIPT_WINDOW
    lines = [text for sec, text in srt_entries if start <= sec <= end]
    return "".join(lines)


def seconds_to_timestamp(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def build_prompt(transcript_context: str) -> str:
    base = PROMPT.rstrip()
    if not transcript_context:
        return base
    return (
        base
        + f"\n\n参考情報として、この画像が撮影された時点（前後{TRANSCRIPT_WINDOW}秒）の音声書き起こしは以下になります\n"
        + f"「{transcript_context}」\n\n"
        + "上記の発話内容を直接的にあなたの説明テキストに含めてはいけませんが、画像を説明する際の参考として利用してください"
    )


def describe_image(image_path: Path, transcript_context: str = "") -> str:
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode()

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": VISION_MODEL,
            "reasoning": {"effort": "minimal"},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_data}",
                                "media_resolution": "low",
                            },
                        },
                        {"type": "text", "text": build_prompt(transcript_context)},
                    ],
                }
            ],
        },
        timeout=60,
    )
    if not response.ok:
        print(f"\nHTTPエラー {response.status_code}: {response.text}")
        response.raise_for_status()

    message = response.json()["choices"][0]["message"]
    thinking = message.get("reasoning", "")
    content = message.get("content", "")

    if thinking:
        return f"（思考過程）{thinking}\n\n{content}"
    return content


def main() -> None:
    if len(sys.argv) < 2:
        print(f"使用方法: {sys.argv[0]} <VOD_ID>")
        sys.exit(1)

    if not OPENROUTER_API_KEY:
        print("エラー: OPENROUTER_API_KEY が .env に設定されていません")
        sys.exit(1)

    vod_id = sys.argv[1]
    captures_dir = CAPTURES_DIR / vod_id

    if not captures_dir.exists():
        print(f"エラー: キャプチャディレクトリが見つかりません: {captures_dir}")
        sys.exit(1)

    images = sorted(captures_dir.glob("*.jpg"))
    if not images:
        print(f"エラー: 画像が見つかりません: {captures_dir}")
        sys.exit(1)

    DESCRIBES_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DESCRIBES_DIR / f"{vod_id}.txt"

    # SRT があればロードしてコンテキスト補完に使う
    srt_path = TRANSCRIPTIONS_DIR / f"{vod_id}.srt"
    srt_entries = []
    if srt_path.exists():
        srt_entries = parse_srt(srt_path)
        print(f"SRT読み込み完了: {srt_path} ({len(srt_entries)}エントリ)")
    else:
        print(f"SRTなし（コンテキストなしで説明生成）: {srt_path}")

    print(f"使用モデル: {VISION_MODEL}")
    print(f"画像数: {len(images)} 枚")

    with open(output_path, "w", encoding="utf-8") as f:
        for image_path in images:
            seconds = int(image_path.stem)
            timestamp = seconds_to_timestamp(seconds)
            print(f"  [{timestamp}] 説明生成中...", end="", flush=True)

            context = get_context_transcript(srt_entries, seconds)
            prompt = build_prompt(context)
            print(f"\n--- プロンプト [{timestamp}] ---\n{prompt}\n--- プロンプトここまで ---\n")
            description = describe_image(image_path, context)

            f.write(f"[{timestamp}]\n{description}\n\n")
            f.flush()
            print(" 完了")

    print(f"説明生成完了: {output_path}")


if __name__ == "__main__":
    main()
