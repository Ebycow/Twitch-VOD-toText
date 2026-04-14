import re
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ====== 設定 ======
COMMENTS_DIR = Path("comments")
TRANSCRIPTIONS_DIR = Path("transcriptions")
OUTPUT_DIR = Path("output")
DESCRIBES_DIR = Path("describes")

# 無視するワード（部分一致でその行を除外）
# Whisperの誤認識で頻出するパターンを標準で記述しています
IGNORE_WORDS = [
    "ご視聴ありがとうございました",
    "ご視聴いただき",
    "チャンネル登録",
    "動画でお会いしましょう",
    "音量を変えてみます",
    "音量を調整します",
    "おやすみなさい",
    "お疲れ様でした",
    "おつかれさまでした",
    "次回予告"


]


def parse_srt(filepath):
    """SRTファイルをパースして (秒数, タイムスタンプ文字列, テキスト) のリストを返す"""
    entries = []
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    blocks = re.split(r"\n\n+", content.strip())
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        time_match = re.match(r"(\d{2}):(\d{2}):(\d{2}),\d+", lines[1])
        if not time_match:
            continue
        h, m, s = int(time_match.group(1)), int(time_match.group(2)), int(time_match.group(3))
        total_seconds = h * 3600 + m * 60 + s
        text = "\n".join(lines[2:]).strip()
        timestamp_str = f"{h:02d}:{m:02d}:{s:02d}"
        entries.append((total_seconds, timestamp_str, text))

    return entries


def parse_chat_json(filepath):
    """JSONチャットファイルをパースしてメタデータとコメントリストを返す"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    video = data.get("video", {})
    streamer = data.get("streamer", {})

    metadata = {
        "title": video.get("title", ""),
        "streamer": streamer.get("name", ""),
        "game": video.get("game", ""),
        "created_at": video.get("created_at", ""),
        "length": video.get("length", 0),
        "view_count": video.get("viewCount", 0),
    }

    comments = []
    commenter_counts = {}
    for c in data.get("comments", []):
        total_sec = int(c.get("content_offset_seconds", 0))
        display_name = c.get("commenter", {}).get("display_name", "")
        body = c.get("message", {}).get("body", "")
        if display_name and body:
            comments.append((total_sec, display_name, body))
            commenter_counts[display_name] = commenter_counts.get(display_name, 0) + 1

    metadata["commenter_counts"] = commenter_counts
    return metadata, comments


def filter_repeated_srt(entries):
    """同じテキストが5回以上連続する場合はそのブロックを除外する"""
    result = []
    i = 0
    while i < len(entries):
        text = entries[i][2]
        j = i
        while j < len(entries) and entries[j][2] == text:
            j += 1
        if j - i < 2:
            result.extend(entries[i:j])
        i = j
    return result


def should_ignore(text):
    """テキストに無視ワードが含まれているか"""
    return any(word in text for word in IGNORE_WORDS)


def parse_describes(filepath):
    """describes ファイルをパースして (秒数, テキスト) のリストを返す。
    フォーマット:
        [HH:MM:SS]
        説明テキスト（複数行可）

        [HH:MM:SS]
        次の説明テキスト
    """
    entries = []
    current_seconds = None
    current_lines = []

    def _flush():
        if current_seconds is not None:
            text = "\n".join(current_lines).strip()
            if text:
                entries.append((current_seconds, text))

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            m = re.match(r"^\[(\d{2}):(\d{2}):(\d{2})\]$", line)
            if m:
                _flush()
                h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
                current_seconds = h * 3600 + mi * 60 + s
                current_lines = []
            else:
                if current_seconds is not None:
                    current_lines.append(line)

    _flush()
    return entries


def format_duration(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}時間{m:02d}分{s:02d}秒"
    return f"{m}分{s:02d}秒"


def format_created_at(created_at_str):
    try:
        dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        jst = dt.astimezone(timezone(timedelta(hours=9)))
        return jst.strftime("%Y年%m月%d日 %H:%M JST")
    except Exception:
        return created_at_str


def merge_and_output(srt_path, json_path, output_path, describes_path=None):
    srt_entries = filter_repeated_srt(parse_srt(srt_path))
    metadata, comment_entries = parse_chat_json(json_path)

    merged = []

    # source の優先順: -1=画面説明, 0=文字起こし, 1=チャット
    for total_sec, ts, text in srt_entries:
        if should_ignore(text):
            continue
        merged.append((total_sec, 0, text))

    for total_sec, username, comment in comment_entries:
        if should_ignore(comment):
            continue
        formatted = f'\nここで{username}がコメント: "{comment}"\n'
        merged.append((total_sec, 1, formatted))

    if describes_path and describes_path.exists():
        for total_sec, description in parse_describes(describes_path):
            merged.append((total_sec, -1, description))
        print(f"画面説明を読み込みました: {describes_path}")

    # タイムスタンプでソート（同じ時間なら画面説明→文字起こし→チャットの順）
    merged.sort(key=lambda x: (x[0], x[1]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        # メタデータヘッダー
        if metadata.get("title"):
            f.write(f"タイトル: {metadata['title']}\n")
        if metadata.get("streamer"):
            f.write(f"配信者: {metadata['streamer']}\n")
        if metadata.get("game"):
            f.write(f"ゲーム: {metadata['game']}\n")
        if metadata.get("created_at"):
            f.write(f"配信日時: {format_created_at(metadata['created_at'])}\n")
        if metadata.get("length"):
            f.write(f"配信時間: {format_duration(metadata['length'])}\n")
        # if metadata.get("view_count"):
        #     f.write(f"視聴数: {metadata['view_count']:,}\n")
        counts = metadata.get("commenter_counts", {})
        if counts:
            sorted_commenters = sorted(counts.items(), key=lambda x: x[1], reverse=True)
            f.write(f"コメントユーザー ({len(sorted_commenters)}人):\n")
            for name, cnt in sorted_commenters:
                f.write(f"  {name}: {cnt}回\n")
        f.write("\n" + "=" * 40 + "\n\n")

        last_marker = -1
        last_srt_sec = None
        for total_sec, source, line in merged:
            if source == 0 and last_srt_sec is not None:
                gap = total_sec - last_srt_sec
                if gap >= 60:
                    minutes = gap // 60
                    f.write(f"\n（{minutes}分無音）\n\n")
                elif gap > 5:
                    f.write("\n")
            if source == 0:
                last_srt_sec = total_sec
            marker = total_sec // 600  # 10分 = 600秒
            if marker > last_marker:
                total_minutes = marker * 10
                if total_minutes >= 60:
                    h = total_minutes // 60
                    m = total_minutes % 60
                    elapsed = f"{h}時間{m}分" if m else f"{h}時間"
                else:
                    elapsed = f"{total_minutes}分"
                if last_marker >= 0:
                    f.write("\n")
                f.write(f"～ 配信開始から{elapsed}経過 ～\n\n")
                last_marker = marker
            if source == -1:
                f.write(f"【現状の配信画面の説明】\n{line}\n【配信画面の説明ここまで】\n")
            else:
                f.write(line + "\n")

    print(f"出力完了: {output_path} ({len(merged)}行)")


def main():
    import sys
    if len(sys.argv) < 2:
        print(f"使用方法: {sys.argv[0]} <stem>")
        print("例: python3 merge.py 2393832961")
        sys.exit(1)

    stem = sys.argv[1]

    srt_file = TRANSCRIPTIONS_DIR / f"{stem}.srt"
    json_file = COMMENTS_DIR / f"{stem}.json"

    if not srt_file.exists():
        print(f"SRTファイルが見つかりません: {srt_file}")
        sys.exit(1)
    if not json_file.exists():
        print(f"対応するJSONファイルが見つかりません: {json_file}")
        sys.exit(1)

    output_file = OUTPUT_DIR / f"{stem}.txt"
    describes_file = DESCRIBES_DIR / f"{stem}.txt"
    merge_and_output(srt_file, json_file, output_file, describes_file)


if __name__ == "__main__":
    main()
