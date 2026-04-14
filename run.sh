#!/bin/bash
set -euo pipefail

# ====== 使用方法 ======
# ./run.sh <VOD_ID>
# 例: ./run.sh 2393832961

VOD_ID="${1:-}"
OMIT_VLM=""

for arg in "$@"; do
    case "$arg" in
        --omit-vlm) OMIT_VLM="1" ;;
        *) ;;
    esac
done

if [ -z "$VOD_ID" ] || [ "$VOD_ID" = "--omit-vlm" ]; then
    echo "使用方法: $0 <VOD_ID> [--omit-vlm]"
    exit 1
fi

echo "=== [DEBUG] run.sh 受け取った引数: $*"
echo "=== [DEBUG] OMIT_VLM='$OMIT_VLM'"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMMENTS_DIR="$SCRIPT_DIR/comments"
AUDIOS_DIR="$SCRIPT_DIR/audios"
TRANSCRIPTIONS_DIR="$SCRIPT_DIR/transcriptions"
OUTPUT_DIR="$SCRIPT_DIR/output"
CAPTURES_DIR="$SCRIPT_DIR/captures"
DESCRIBES_DIR="$SCRIPT_DIR/describes"
mkdir -p "$COMMENTS_DIR" "$AUDIOS_DIR" "$TRANSCRIPTIONS_DIR" "$OUTPUT_DIR" "$CAPTURES_DIR" "$DESCRIBES_DIR"

TWITCH_DL="$SCRIPT_DIR/TwitchDownloaderCLI"

M4A="$AUDIOS_DIR/${VOD_ID}.m4a"
WAV="$AUDIOS_DIR/${VOD_ID}.wav"
CHAT="$COMMENTS_DIR/${VOD_ID}.json"
SRT_BASE="$TRANSCRIPTIONS_DIR/${VOD_ID}"

# ====== 1. 音声ダウンロード ======
echo "=== [1/7] 音声ダウンロード中 (VOD: $VOD_ID) ==="
"$TWITCH_DL" videodownload \
    -u "$VOD_ID" \
    -o "$M4A" \
    --collision Overwrite

# ====== 2. チャットダウンロード ======
echo "=== [2/7] チャットダウンロード中 ==="
"$TWITCH_DL" chatdownload \
    -u "$VOD_ID" \
    -o "$CHAT" \
    --collision Overwrite

# ====== 3. m4a → wav 変換 ======
echo "=== [3/7] WAV変換中 (16kHz mono) ==="
ffmpeg -y -i "$M4A" -ar 16000 -ac 1 "$WAV"

# ====== 4. Whisper 文字起こし → SRT生成 ======
echo "=== [4/7] 文字起こし中 (whisperx) ==="
WHISPER_PROMPT=$(python3 - "$CHAT" <<'EOF'
import json, sys
from collections import Counter
with open(sys.argv[1]) as f:
    d = json.load(f)
streamer = d.get("streamer", {}).get("name", "")
title    = d.get("video",    {}).get("title", "")
game     = d.get("video",    {}).get("game",  "")
counts = Counter(
    c["commenter"]["display_name"]
    for c in d.get("comments", [])
    if c.get("commenter", {}).get("display_name")
)
top3 = [name for name, _ in counts.most_common(3)]
parts = []
if streamer:
    parts.append(f"配信者は{streamer}")
if title:
    parts.append(f"配信タイトルは「{title}」")
if game:
    parts.append(f"ゲームは{game}")
if top3:
    parts.append(f"よくコメントしていた視聴者は{'、'.join(top3)}です")
print("これはTwitch配信の書き起こしです。" + "、".join(parts) + "。")
EOF
)
WHISPER_PROMPT="${WHISPER_PROMPT} えー、あのー、んー、えっと などのフィラーも省略せず書き起こしてください。"
echo "Whisperプロンプト: $WHISPER_PROMPT"
whisperx "$WAV" \
    --model large-v3 \
    --language ja \
    --device cuda \
    --compute_type float16 \
    --batch_size 16 \
    --initial_prompt "$WHISPER_PROMPT" \
    --output_format srt \
    --output_dir "$TRANSCRIPTIONS_DIR" \
    --align_model "facebook/mms-1b-all" \
    --vad_method pyannote \
    --beam_size 3 \
    --best_of 3 \
    --temperature 0.2

# ====== 5. フレームキャプチャ ======
cd "$SCRIPT_DIR"
echo "=== [5/7] フレームキャプチャ中 (capture.py) ==="
python3 capture.py "$VOD_ID"

# ====== 6. 画面説明生成 ======
if [ -n "$OMIT_VLM" ]; then
    echo "=== [6/7] 画面説明生成をスキップ (--omit-vlm) ==="
else
    echo "=== [6/7] 画面説明生成中 (describe.py) ==="
    python3 describe.py "$VOD_ID"
fi

# ====== 7. merge.py でコメント+書き起こし+画面説明合成 ======
echo "=== [7/7] マージ中 (merge.py) ==="
python3 merge.py "$VOD_ID"

echo ""
echo "完了! 出力: $OUTPUT_DIR/${VOD_ID}.txt"
