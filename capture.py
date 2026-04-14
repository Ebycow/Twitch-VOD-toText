#!/usr/bin/env python3
"""
capture.py - Twitch VOD から 10 分おきにフレームをキャプチャする
使用方法: python3 capture.py <VOD_ID>
出力:     captures/<VOD_ID>/<秒数6桁>.jpg
"""
import json
import subprocess
import sys
from pathlib import Path

INTERVAL = 600  # 10分 = 600秒
SCRIPT_DIR = Path(__file__).parent
CAPTURES_DIR = SCRIPT_DIR / "captures"


def get_vod_duration(vod_id: str) -> int:
    """yt-dlp で VOD のメタデータを取得して動画長（秒）を返す"""
    url = f"https://www.twitch.tv/videos/{vod_id}"
    print(f"VOD情報取得中: {url}")
    result = subprocess.run(
        ["yt-dlp", "--dump-json", "--no-download", url],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(result.stdout)
    return int(info["duration"])


def get_stream_url(vod_id: str) -> str:
    """yt-dlp でベスト画質のストリーム URL を取得する"""
    url = f"https://www.twitch.tv/videos/{vod_id}"
    result = subprocess.run(
        ["yt-dlp", "-g", "-f", "best", url],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def capture_frame(stream_url: str, seconds: int, output_path: Path) -> None:
    """ffmpeg で指定秒数のフレームを 1 枚抽出する"""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", str(seconds),
            "-i", stream_url,
            "-frames:v", "1",
            "-q:v", "2",
            str(output_path),
        ],
        check=True,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    if len(sys.argv) < 2:
        print(f"使用方法: {sys.argv[0]} <VOD_ID>")
        sys.exit(1)

    vod_id = sys.argv[1]
    output_dir = CAPTURES_DIR / vod_id
    output_dir.mkdir(parents=True, exist_ok=True)

    duration = get_vod_duration(vod_id)
    h, m, s = duration // 3600, (duration % 3600) // 60, duration % 60
    print(f"動画時間: {h}時間{m:02d}分{s:02d}秒 ({duration}秒)")

    timestamps = list(range(0, duration + 1, INTERVAL))
    print(f"キャプチャ予定: {len(timestamps)} 枚")

    stream_url = get_stream_url(vod_id)

    for t in timestamps:
        th, tm, ts = t // 3600, (t % 3600) // 60, t % 60
        output_path = output_dir / f"{t:06d}.jpg"
        print(f"  [{th:02d}:{tm:02d}:{ts:02d}] キャプチャ中 → {output_path.name}")
        capture_frame(stream_url, t, output_path)

    print(f"キャプチャ完了: {output_dir} ({len(timestamps)} 枚)")


if __name__ == "__main__":
    main()
