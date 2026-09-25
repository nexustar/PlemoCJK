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

## Building PlemoCJK (regional subfonts)

PlemoCJK builds SC / TC / JP / KR regional subfonts. The process is similar
to upstream, with additional steps for fetching source fonts and preparing
per-region CJK input fonts.

```bash
# 1. Fetch source fonts (SC/TC/KR download + SHA-256 verification; JP is in the repo)
python3 fetch_sources.py

# 1b. Regenerate SC Text from the Glyphs master at weight 450
#     (IBM release uses 425, ~5% thinner than JP/TC)
#     The master zip is 186MB; fontmake needs a few minutes and ~3GB memory
pip install "fontmake[pathops]"
python3 regen_sc_text.py

# 2. Build (make.sh also calls prepare_cjk.py)
docker run --rm -v "$(pwd):/work" ghcr.io/yuru7/composite-font-builder

# 3. Bundle 4 regions into a single TTC (needs node on the host)
npm install
node --max-old-space-size=8192 bundle_ttc.mjs

# 4. Check
python3 check_fonts.py --variant default --ttc build/ttc/PlemoCJK-Regular.ttc

# 5. Package (needs zip/unzip on the host)
./release.sh
```

Quick smoke test (one file only):

```bash
docker run --rm -e DEBUG=1 -v "$(pwd):/work" ghcr.io/yuru7/composite-font-builder
```

### make.sh environment variables

| Variable | Description |
|---|---|
| `DEBUG=1` | Regular weight only. If `VARIANTS`/`REGIONS` are not set, builds Term x first region |
| `REGIONS="SC KR"` | Limit regions (default: `[regions] REGIONS` in build.ini) |
| `VARIANTS="Term Natural"` | Specify variants directly |
| `STYLES="Text TextItalic"` | Specify styles (weights) directly. Overrides `DEBUG` and also limits `prepare_cjk.py` |
| `SKIP_PREPARE=1` | Skip `prepare_cjk.py` when `source/prepared/` already exists |
| `MAX_PARALLEL=4` | Parallelism for region x variant |

### Build stages

0. `regen_sc_text.py` produces `source/regenerated/IBMPlexSansSC-Text.ttf`
   (re-interpolates SC Text at weight 450 from the IBM Glyphs master;
   `build.ini` `REGENERATED_STYLES` tells the build to use it instead of the IBM release)
1. `prepare_cjk.py` produces `source/prepared/PlemoCJK-{region}-{style}.ttf`
   (per-region fallback fill + hangul)
2. Build the eng side once per variant
   (`fontforge_script.py --eng-only` + ttfautohint); reused by all 4 regions
3. Build region x variant in parallel
   (`fontforge_script.py --region XX` → `fonttools_script.py <tag> <region>`)


### Webfonts

```bash
pip install "fonttools==4.63.0" brotli
python3 subset_webfont.py build
```

Converts all built default-variant weights and italics; each style must have
SC/TC/JP/KR inputs. Regular-only builds also work. Output:
`build/release/PlemoCJK_webfont_VERSION/PlemoCJK-SC.css` with slices in `SC/`
(likewise TC/JP/KR).
Use `font-family: "PlemoCJK SC", monospace` and select weight/style in CSS.

Each regional CSS includes every generated style. Subsets retain full character
coverage and Google's range priority. The output also carries licenses, a
README and `manifest.json` (source and WOFF2 hashes).

On `v`-prefixed tags the Action packages webfonts into the release and, for
full builds, force-pushes them as a single orphan commit to the `webfonts`
branch. Serve that branch with GitHub Pages (Settings → Pages → branch
`webfonts`, `/`); at ~400 MB it exceeds jsDelivr's 50 MB limit.
