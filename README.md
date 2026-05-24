# kakio

Twitch VOD を音声書き起こし・チャット・画面説明の3つのソースからタイムライン付きテキストに変換するツールです。

## 概要

以下の処理を自動化します:

1. **音声ダウンロード** — TwitchDownloaderCLI で VOD の音声を取得
2. **チャットダウンロード** — 同ツールでチャットログ (JSON) を取得
3. **音声変換** — ffmpeg で WAV (16kHz mono) に変換
4. **文字起こし** — WhisperX で SRT ファイルを生成
5. **フレームキャプチャ** — yt-dlp + ffmpeg で 10 分おきに静止画を抽出
6. **画面説明生成** — OpenRouter 経由の VLM が各フレームを日本語で説明
7. **マージ** — 書き起こし・チャット・画面説明を時系列に結合して 1 つのテキストに出力

## 必要なもの

- Python 3.10+
- [TwitchDownloaderCLI](https://github.com/lay295/TwitchDownloader)（`./TwitchDownloaderCLI` として配置）
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [ffmpeg](https://ffmpeg.org/)
- [WhisperX](https://github.com/m-bain/whisperX)（GPU 推奨）
- [OpenRouter](https://openrouter.ai/) アカウントと API キー（画面説明生成に使用）

## セットアップ

```bash
pip install requests python-dotenv
```

`.env.example` をコピーして `.env` を作成し、API キーを設定します:

```bash
cp .env.example .env
# .env を編集して OPENROUTER_API_KEY を設定
```

## 使い方

```bash
# VOD_ID は Twitch の VOD URL 末尾の数字
./run.sh <VOD_ID>

# 画面説明生成（VLM 呼び出し）をスキップする場合
./run.sh <VOD_ID> --omit-vlm
```

### 各スクリプトを個別に実行

```bash
python3 capture.py <VOD_ID>   # フレームキャプチャのみ
python3 describe.py <VOD_ID>  # 画面説明生成のみ
python3 merge.py <VOD_ID>     # マージのみ
```

## 出力

`output/<VOD_ID>.txt` に以下の形式でタイムライン付きテキストが生成されます:

```
タイトル: ...
配信者: ...
ゲーム: ...
配信日時: ...
配信時間: ...
コメントユーザー (N人):
  ...

========================================

～ 配信開始から10分経過 ～

【現状の配信画面の説明】
...
【配信画面の説明ここまで】
発話テキスト
ここでXXXがコメント: "..."
```

## ディレクトリ構成

```
.
├── run.sh               # メインスクリプト
├── capture.py           # フレームキャプチャ
├── describe.py          # 画面説明生成
├── merge.py             # タイムラインマージ
├── TwitchDownloaderCLI  # 要配置
├── .env                 # API キー（要作成）
├── .env.example
├── audios/              # ダウンロードした音声（自動生成）
├── captures/            # キャプチャ画像（自動生成）
├── comments/            # チャットログ（自動生成）
├── transcriptions/      # SRT ファイル（自動生成）
├── describes/           # 画面説明テキスト（自動生成）
└── output/              # 最終出力（自動生成）
```

## 環境変数

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `OPENROUTER_API_KEY` | OpenRouter の API キー | （必須） |
| `VISION_MODEL` | 画面説明に使用する VLM | `google/gemini-3.1-flash-lite` |
