# 公開ファイル / Published files
## 日本語

| ファイルまたはフォルダ | 説明 |
| --- | --- |
| `Auralis.py` | Auralis 本体のソースコードです。 |
| `Auralis_launcher.py` | Auralis を起動するためのランチャーです。 |
| `assets/` | アイコンや画像などのアセットを格納するディレクトリです。 |
| `Resources/Languages/` | GUI 用の言語定義 JSON ファイルを格納しています。 |
| `Resources/themes/` | GUI テーマ定義用の JSON ファイルを格納しています。 |
| `Resources/presets/` | 音量ノーマライズ機能で使用するプリセット JSON ファイルを格納しています。 |
| `.github/workflows/release.yml` | タグを契機に各プラットフォーム向けの配布物をビルドし，GitHub Release を公開するワークフローです。 |
| `.gitignore` | Git で追跡しないローカル生成物を定義します。 |
| `scripts/build_macos.sh` | PyInstaller を使用して `Auralis.app` を生成する macOS 用ビルドスクリプトです。 |
| `scripts/build_windows.ps1` | PyInstaller を使用して `Auralis.exe` を生成する Windows 用ビルドスクリプトです。 |
| `README.md` | プロジェクト概要、機能、必要環境、実行方法、ビルド方法および配布時の注意事項を記載しています。 |
| `LICENSE` | 本プロジェクトに適用される MIT License を収録しています。 |
| `THIRD_PARTY_NOTICES.md` | 第三者コンポーネントのライセンス情報および配布時の注意事項を記載しています。 |
| `requirements.txt` | Auralis の実行およびビルドに必要な Python パッケージ一覧を記載しています。 |
## English

These files are intended for the public GitHub repository.

| File or Directory | Description |
| --- | --- |
| `Auralis.py` | Main source code of Auralis. |
| `Auralis_launcher.py` | Launcher used to start Auralis. |
| `assets/` | Directory containing icons and other graphical assets. |
| `Resources/Languages/` | JSON language files used for GUI localization. |
| `Resources/themes/` | JSON files defining GUI themes. |
| `Resources/presets/` | JSON preset files used by the loudness normalization feature. |
| `.github/workflows/release.yml` | Workflow that builds platform-specific archives from a tag and publishes a GitHub Release. |
| `.gitignore` | Defines local generated files that Git does not track. |
| `scripts/build_macos.sh` | macOS build script that generates `Auralis.app` using PyInstaller. |
| `scripts/build_windows.ps1` | Windows build script that generates `Auralis.exe` using PyInstaller. |
| `README.md` | Contains the project overview, features, requirements, usage instructions, build procedures, and distribution notes. |
| `LICENSE` | Contains the MIT License applicable to this project. |
| `THIRD_PARTY_NOTICES.md` | Lists third-party components, their licenses, and distribution-related notices. |
| `requirements.txt` | Lists the Python packages required to run and build Auralis. |
