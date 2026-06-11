# Third-party notices / 第三者コンポーネント通知

## 日本語

Auralis のソースコードは MIT License で配布されます。

また，実行時およびビルド時の依存コンポーネントにも，それぞれ個別のライセンスが存在します。

- PySide6 / Qt for Python: LGPL / GPL / 商用 Qt ライセンスの選択肢があります。詳細は Qt for Python のライセンス文書を確認してください。
- mutagen: GPL-2.0-or-later.
- requests: Apache License 2.0.
- urllib3: MIT License.
- Pillow: HPND License.
- FFmpeg / ffprobe: ビルド構成に応じて FFmpeg プロジェクトの LGPL/GPL 条件が適用されます。

アルバム情報は公開音楽メタデータサービスから取得し，利用可能な場合は公開アートワークエンドポイントからカバー画像を取得します。これらのサービスから返されるメタデータやアートワークには，別個の権利や利用条件が存在する場合があります。

バンドル済みバイナリを配布する場合は，このファイルに加えて，実際に同梱する FFmpeg および Qt/PySide6 ビルドで要求されるライセンス文書を含めてください。

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

