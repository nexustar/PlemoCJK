# フォントのビルド手順

## Docker を使ってビルド

Docker を使って PlemolJP をビルドする手順です。

ビルド環境は、公開イメージ [`ghcr.io/yuru7/composite-font-builder`](https://github.com/yuru7/composite-font-builder/pkgs/container/composite-font-builder) を使います。`make.sh` やソースフォントなどプロジェクト固有のファイルは、実行時にリポジトリをマウントして渡します。

### 必要なもの

- [Docker](https://docs.docker.com/get-docker/)
- `zip` / `unzip`（`release.sh` が配布用アーカイブの作成と検査に使います。ビルドイメージには入っていないので、ホスト側に入れてください。Debian/Ubuntu なら `sudo apt-get install -y zip unzip`）

ソースフォント（IBM Plex Mono / Sans JP など）は本プロジェクトの `source/` に含まれている前提です。

### フォントを生成する

リポジトリのルートで実行します。初回はイメージの取得が行われ、コンテナ起動時に `./make.sh` が走ります。

```bash
docker run --rm -v "$(pwd):/work" ghcr.io/yuru7/composite-font-builder
```

生成された TTF はホスト側の `./build/` に出力されます。完了まで数分かかります。

他の合成フォントリポジトリでも、同じイメージを使い、そのリポジトリのルートで同様に `docker run` すればビルドできます（そのリポジトリに実行可能な `make.sh` がある前提です）。

デバッグ用に素早く確認するため1ファイルだけ生成するコマンドは以下です。

```bash
docker run --rm -e DEBUG=1 -v "$(pwd):/work" ghcr.io/yuru7/composite-font-builder
```

### 出力について

`make.sh` は最大 4 並列で、通常版・35 幅版・Console・HS・Nerd Fonts など各バリアントをビルドします。

```
build/PlemolJP*.ttf
```

## Docker を使わない場合（参考）

### Linux

Ubuntu 24.04 系では、おおむね次のパッケージが必要です。

```bash
sudo apt-get update
sudo apt-get install -y fontforge python3 python3-fontforge python3-pip ttfautohint zip unzip
python3 -m pip install --break-system-packages fonttools ttfautohint-py
./make.sh
```

依存パッケージの定義は [composite-font-builder](https://github.com/yuru7/composite-font-builder) を参照してください。

### Windows

従来どおり PowerShell から実行できます（FontForge Builds と Python 3 がインストールされていることが前提です）。

```powershell
.\make.ps1
```

こちらは全バリアントを並列ビルドし、`release_files/` 以下に整理して出力します。

---

## PlemoCJK (地域別サブフォント) のビルド

PlemoCJK では SC / TC / JP / KR の 4 地域サブフォントを作ります。
手順は上流とほぼ同じですが、前段にソースフォントの取得と
地域別 CJK 側入力フォントの生成が入ります。

```bash
# 1. ソースフォントを取得する (SC/TC/KR をダウンロード + SHA-256 検証、JP はリポジトリ内)
python3 fetch_sources.py

# 1b. SC の Text だけ IBM の Glyphs 母版から補間位置 450 で作り直す
#     (IBM 発布件は 425 で JP/TC より約 5% 細い。詳細は docs/PlemoCJK-plan.md §6.1)
#     母版の zip が 186MB、fontmake に数分と 3GB 程度のメモリが必要
pip install "fontmake[pathops]"
python3 regen_sc_text.py

# 2. ビルド (make.sh が prepare_cjk.py も呼ぶ)
docker run --rm -v "$(pwd):/work" ghcr.io/yuru7/composite-font-builder

# 3. 4 地域を 1 つの TTC にまとめる (ホスト側で node を使う)
npm install
node --max-old-space-size=8192 bundle_ttc.mjs

# 4. 検査
python3 check_fonts.py --variant Console --ttc build/ttc/PlemoCJKConsole-Regular.ttc

# 5. 配布物を作る (ホスト側で zip / unzip を使う)
./release.sh
```

デバッグ用に 1 ファイルだけ作る場合:

```bash
docker run --rm -e DEBUG=1 -v "$(pwd):/work" ghcr.io/yuru7/composite-font-builder
```

### make.sh の環境変数

| 変数 | 意味 |
|---|---|
| `DEBUG=1` | Regular ウェイトのみ。`VARIANTS`/`REGIONS` 未指定なら Console x 先頭地域の 1 ファイル |
| `REGIONS="SC KR"` | 地域を絞る (既定は build.ini の `[regions] REGIONS`) |
| `VARIANTS="Console ConsoleNF"` | バリアントを直接指定 |
| `STYLES="Text TextItalic"` | スタイル (ウェイト) を直接指定。`DEBUG` より優先し、`prepare_cjk.py` に渡すウェイトもこれに揃う |
| `VARIANT_SET=full` | 35 幅版と HS 版も作る |
| `SKIP_PREPARE=1` | `source/prepared/` が既にある場合に prepare_cjk.py を飛ばす |
| `MAX_PARALLEL=4` | 地域 x バリアントの並列数 |

### ビルドの段構成

0. `regen_sc_text.py` が `source/regenerated/IBMPlexSansSC-Text.ttf` を作る
   (IBM の母版から補間位置 450 で SC の Text だけ作り直す。`build.ini` の
   `REGENERATED_STYLES` がこの 1 ウェイトを発布件の代わりに使うよう指示している)
1. `prepare_cjk.py` が `source/prepared/PlemoCJK-{region}-{style}.ttf` を作る
   (地域ごとの回退補入 + ハングル)
2. バリアントごとに英数字側を 1 回だけ作る
   (`fontforge_script.py --eng-only` → ttfautohint)。4 地域で同じファイルを使い回す
3. 地域 x バリアントを並列でビルド
   (`fontforge_script.py --region XX` → `fonttools_script.py <tag> <region>`)

詳細は [docs/PlemoCJK-plan.md](docs/PlemoCJK-plan.md) を参照。
