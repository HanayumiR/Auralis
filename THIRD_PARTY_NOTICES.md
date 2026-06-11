# 第三者コンポーネントに関する通知 / Third-party notices

## 日本語


Auralis のソースコードは MIT License の下で配布されます。

また，実行時およびビルド時の依存コンポーネントにも，それぞれ独自のライセンスが適用されます。

- PySide6 / Qt for Python:
  LGPL，GPL，または商用 Qt ライセンスのいずれかが適用されます。
  詳細は Qt for Python のライセンス文書を参照してください。
- mutagen: GPL-2.0-or-later
- requests: Apache License 2.0
- urllib3: MIT License
- Pillow: HPND License
- FFmpeg / ffprobe: ビルド構成に応じて FFmpeg プロジェクトによる LGPL/GPL ライセンス条件が適用されます。

バンドル済み実行ファイルを配布する場合は，このファイルに加え，実際に同梱する FFmpeg および Qt/PySide6 のビルドに対応したライセンス文書も必ず同梱してください。

アルバムのメタデータは公開されている楽曲情報メタデータサービスから取得され，カバーアートが利用可能な場合，公開されているカバーアート提供サービスから取得されます。
これらのサービスによって提供されるメタデータやアートワークには，別途権利や利用条件が適用される場合があります。

## English

Auralis source code is distributed under the MIT License.

Runtime and build dependencies keep their own licenses:

- PySide6 / Qt for Python: LGPL / GPL / commercial Qt licensing options. See the Qt for Python license documentation for details.
- mutagen: GPL-2.0-or-later.
- requests: Apache License 2.0.
- urllib3: MIT License.
- Pillow: HPND License.
- FFmpeg / ffprobe: licensed by the FFmpeg project under LGPL/GPL terms depending on the build configuration.

Album metadata is queried from public music metadata services, and cover art is fetched from public cover-art endpoints when available. Metadata and artwork returned by those services may have separate rights and usage terms.

If you distribute a bundled binary, include this file and the license texts required by the exact FFmpeg and Qt/PySide6 builds you ship.

