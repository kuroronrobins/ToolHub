# Build and Release

## Development Start

```powershell
python main.py --dev
```

補助スクリプト:

```powershell
.\scripts\dev_start.ps1
```

## Release Build

```powershell
.\scripts\build_release.ps1
```

初回実装ではTauri buildを呼び出す構造までを用意します。完全な配布パッケージ化、署名、更新配布は今後の作業です。

## main.py Release Search

`python main.py` は以下の順でビルド済み実行ファイルを探します。

- `launcher/src-tauri/target/release/toolhub.exe`
- `launcher/src-tauri/target/release/ToolHub.exe`
- `release/ToolHub.exe`
- `dist/ToolHub.exe`

見つからない場合は開発モードに切り替えます。`--release` 指定時は開発モードへ切り替えません。

## Release Manifest

`release/manifest.json` は将来の更新確認用の雛形です。

```json
{
  "launcher": {
    "name": "ToolHub",
    "version": "0.1.0"
  },
  "apps": {}
}
```

将来はここに各アプリの配布バージョン、ハッシュ、取得先を追加できます。

