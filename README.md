# SubHub — 媒体库字幕搜索与下载工具

> 🎬 一键为你的 Jellyfin / Emby / Plex 媒体库(含 **STRM 虚拟文件**)自动搜索并下载字幕,字幕自动落到媒体同目录,播放器直接识别。
> 🐳 基于 Docker,两条命令即可跑起来,无需懂代码。

---

## 目录

- [SubHub 是什么?](#subhub-是什么)
- [功能特性](#功能特性)
- [支持的 5 个字幕源](#支持的-5-个字幕源)
- [一、新手快速上手(Docker 部署)](#一新手快速上手docker-部署)
- [二、打开网页开始使用](#二打开网页开始使用)
- [三、字幕源配置详解](#三字幕源配置详解)
- [四、STRM 虚拟文件支持](#四strm-虚拟文件支持)
- [五、常用环境变量](#五常用环境变量)
- [六、对外 API(进阶)](#六对外-api进阶)
- [七、常见问题(FAQ)](#七常见问题faq)
- [八、本地开发与测试](#八本地开发与测试)
- [九、项目结构](#九项目结构)
- [版本记录](#版本记录)

---

## SubHub 是什么?

SubHub 是一个**自托管的字幕聚合下载工具**。它做三件事:

1. **扫描**你的媒体库(视频文件,以及 `.strm` 虚拟文件);
2. **搜索**多个字幕网站/API,把结果聚合展示在一个网页里;
3. **一键下载**字幕,自动命名并放到媒体文件旁边(如 `Movie.mkv` → `Movie.srt`、`Movie.strm` → `Movie.srt`),Jellyfin/Emby/Plex 立刻就能识别并加载。

它与你常见的字幕工具思路一致,但代码完全独立开发,支持 **STRM 虚拟文件**(云盘/网盘挂载场景必备)。

---

## 功能特性

| 特性 | 说明 |
| --- | --- |
| 🖱️ **STRM 支持** | 将 `.strm` 当作媒体文件:标题从 strm 指向的目标文件名解析,字幕落位到 strm 同目录同主名 |
| 🔎 **多源聚合** | 并行搜索多个字幕源,结果合并展示,带搜索缓存(10 分钟) |
| ⬇️ **智能落位** | strm 字幕保存为 `同目录/同主名`;媒体目录只读时自动回退到字幕目录 |
| 🧾 **正则标题识别** | 内置常见命名规则,可在设置页自定义、在线测试 |
| 🗄️ **SQLite 持久化** | API 令牌、源开关、凭据、正则、缓存、历史记录全部本地存储 |
| 📱 **响应式界面** | 原生单页应用:媒体 / 字幕 / 设置三个页面 |
| 🔐 **API 鉴权** | 对外 API 使用 Bearer Token,首次启动自动生成 |
| 🐳 **Docker 一键部署** | 自带 Dockerfile 与 Compose,非 root 用户运行 |

---

## 支持的 5 个字幕源

| 源 | 需要配置吗? | 说明 |
| --- | --- | --- |
| **字幕库(zimuku)** | ❌ 免配置 | 自动识别网站验证码并放行,搜索 / 下载 / 7z 解压全自动 |
| **SubHD** | ❌ 免配置 | 开箱即用 |
| **assrt(射手网)** | ✅ 需 Token | 免费注册获取 |
| **OpenSubtitles 网页版** | ✅ 需 FlareSolverr | 网站有反爬,需自建 FlareSolverr 服务配合 |
| **OpenSubtitles API** | ✅ 需官方凭据 | API Key + 用户名 + 密码 |

> ⚠️ 本项目**不包含任何成人内容字幕源**。

---

## 一、新手快速上手(Docker 部署)

> 全程大约 10 分钟,不需要安装 Python,不需要写代码。

### 第 1 步:安装 Docker

- **Windows**:安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)(安装后启动,若提示 WSL2 按提示启用并重启)。
- **macOS**:同样安装 Docker Desktop。
- **Linux(Ubuntu/Debian)**:
  ```bash
  sudo apt update
  sudo apt install -y docker.io docker-compose-plugin
  sudo systemctl enable --now docker
  ```
- 验证安装:`docker --version` 能输出版本号即可。

### 第 2 步:下载项目

```bash
git clone https://github.com/<你的GitHub用户名>/subhub.git
cd subhub
```

> 不会用 git?也可以直接点 GitHub 页面上的 **Code → Download ZIP**,解压后进入文件夹。

### 第 3 步:创建数据目录

```bash
mkdir -p media data
```

- `media/`:放你的媒体文件或 strm 文件(也可以把整个媒体库目录映射进来,见下文);
- `data/`:存放数据库、API 令牌、无媒体场景下下载的字幕。

### 第 4 步:启动

```bash
docker compose up -d --build
```

第一次构建需要下载依赖,大约 5~15 分钟(取决于网络)。看到 `Started` 或 `done` 即成功。

### 第 5 步:打开网页

浏览器访问 <http://localhost:8000>,看到"媒体"页面即部署成功。

> 如果 SubHub 与媒体库不在同一台机器,请把 `docker-compose.yml` 里的 `/media` 映射改成你实际的媒体路径(见"目录映射")。

---

## 二、打开网页开始使用

界面分三个页面:

### 🎬 媒体页(默认)
- 自动扫描 `media/` 目录下的视频与 strm 文件,以卡片展示(带封面);
- 点击卡片上的 **搜索字幕** 按钮,自动用解析出的片名搜索。

### 🔎 字幕页
- 手动输入片名(如 `十二生肖`),点击 **搜索字幕**;
- 结果按来源标注(字幕库 / SubHD / assrt / OpenSubtitles…),点击 **下载** 即可;
- 从媒体卡片进入时,字幕会自动保存到媒体同目录;手动搜索则保存到 `data/downloads/`。

### ⚙️ 设置页
- **字幕源开关**:勾选要使用的源(至少开一个才能搜索);
- **assrt Token**、**FlareSolverr 地址**、**OpenSubtitles API 凭据**:按下方说明填写;
- **媒体名称识别正则**:可添加/删除规则,并输入文件名测试识别结果。

---

## 三、字幕源配置详解

### 1. 字幕库(zimuku) — 免配置

默认开启。网站有云锁验证码,SubHub 用 OCR 自动识别并放行,无需任何操作。
> 若网站升级反爬导致放行失败,搜索会如实报错"zimuku 验证码放行失败",稍后重试即可。

### 2. SubHD — 免配置

默认开启,开箱即用。

### 3. assrt(射手网)

1. 打开 <https://assrt.net/> 注册账号;
2. 登录后进入个人中心,复制你的 **Token**;
3. 在 SubHub 设置页粘贴 Token 并保存,自动开启该源。

### 4. OpenSubtitles 网页版(需要 FlareSolverr)

该源通过抓取 opensubtitles.org 网页实现,但网站有反爬校验,需要先自建一个 [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) 服务:

```bash
docker run -d --name flaresolverr -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest
```

然后:
1. 确认 FlareSolverr 已启动(浏览器访问 `http://<你的IP>:8191` 有响应);
2. 在 SubHub 设置页的 **OpenSubtitles 网页版** 输入框填写地址,如 `http://192.168.1.10:8191`(局域网内用宿主机 IP,不要填 localhost);
3. 保存后自动开启该源。

> FlareSolverr 与 SubHub 在同一台机器时,若用 docker compose 部署,可将 FlareSolverr 加入同一网络并用服务名 `http://flaresolverr:8191`。

### 5. OpenSubtitles API(官方接口)

1. 打开 <https://www.opensubtitles.com/> 注册;
2. 生成 **API Key**;
3. 在 SubHub 设置页填写 **API Key + 用户名 + 密码** 并保存。

> 若提示"必须全部填写",三个字段都填上即可。

---

## 四、STRM 虚拟文件支持

STRM 是"指针文件":里面只有一行目标地址(网盘/云盘/远程媒体库的链接),配合 rclone 等挂载方案可让 Jellyfin 直接播放云端视频。SubHub 对 strm 做了专门支持:

- **扫描**:strm 文件与普通视频一样出现在媒体页;
- **标题解析**:从 strm 内容解析目标文件名(`http://nas:8096/videos/1/Movie.mkv` → `Movie`),失败则回退文件名;
- **封面匹配**:按解析出的媒体主名匹配同目录封面(`Movie (2012).jpg` 等);
- **字幕落位**:从 strm 卡片搜索并下载,字幕保存到 **strm 同目录、同主名**:
  ```
  Movie.strm  →  Movie.srt      (普通)
  Movie.strm  →  Movie.chs.srt  (保留语言标签)
  ```
- **只读回退**:媒体目录是只读挂载时,自动改存到 `data/downloads/` 并在界面提示。

---

## 五、常用环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MEDIA_DIR` | `/media` | 媒体库目录(容器内) |
| `DATA_DIR` | `/data` | 数据目录(容器内) |
| `API_TOKEN` | 自动生成 | 对外 API 令牌;不填则自动生成并写入 `data/api-token` |
| `REQUEST_TIMEOUT` | `25` | 请求超时(秒) |
| `MAX_SEARCH_PAGES` | `1` | 每个源搜索页数 |
| `SEARCH_CACHE_TTL` | `600` | 搜索缓存时长(秒) |
| `SUBHD_BASE` | `https://subhd.tv` | SubHD 站点地址(镜像场景可改) |
| `ZIMUKU_BASE` | `https://zimuku.org` | 字幕库站点地址 |
| `ASSRT_API_BASE` | `https://api.assrt.net` | assrt API 地址 |
| `OPENSUBTITLES_API_BASE` | `https://api.opensubtitles.com` | OpenSubtitles API 地址 |

> 想要 API 令牌固定不变,可在 `docker-compose.yml` 的 `environment` 里加 `API_TOKEN: 你的令牌`。

---

## 六、对外 API(进阶)

除网页界面外,所有功能都有 HTTP API(除 `/api/health` 外都需要 `Authorization: Bearer <令牌>`):

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/media` | 媒体列表 |
| `GET` | `/api/search?keyword=片名&source=zimuku` | 搜索字幕(`source` 可多个) |
| `POST` | `/api/download` | 下载字幕 |
| `GET` | `/api/history/downloads` | 下载历史 |
| `GET` | `/api/history/searches` | 搜索历史 |
| `DELETE` | `/api/cache/search` | 清空搜索缓存 |
| `GET` | `/api/database/stats` | 数据库统计 |
| `GET/PUT` | `/api/settings/providers` | 字幕源开关 |
| `GET/PUT/DELETE` | `/api/settings/assrt` | assrt Token |
| `GET/PUT` | `/api/settings/opensubtitles` | FlareSolverr 地址 |
| `GET/PUT/DELETE` | `/api/settings/opensubtitles-api` | OpenSubtitles API 凭据 |

下载示例:

```bash
curl -X POST http://localhost:8000/api/download \
  -H "Authorization: Bearer $(cat data/api-token)" \
  -H "Content-Type: application/json" \
  -d '{"provider":"subhd","subtitle_id":"12345","title":"十二生肖","media_id":"TW92aWUuc3RybQ"}'
```

---

## 七、常见问题(FAQ)

**Q: 网页打不开?**
检查容器是否运行:`docker compose ps`。若状态不是 `Up`,查看日志:`docker compose logs -f`。

**Q: 搜索没结果?**
先在设置页确认至少开启一个字幕源;部分网站对无人值守访问敏感,可稍后重试。

**Q: zimuku 报"验证码放行失败"?**
网站验证码升级或识别失败,属正常波动,稍后重试;持续失败可先关闭该源使用其他源。

**Q: OpenSubtitles 网页版报 FlareSolverr 错误?**
确认 FlareSolverr 容器在运行、地址填写正确(局域网填宿主机 IP,别用 localhost)、端口 8191 可访问。

**Q: strm 的字幕下载到哪里了?**
strm 同目录、同主名(`Movie.strm` → `Movie.srt`)。若媒体目录只读,会落到 `data/downloads/` 并在界面提示。

**Q: 字幕文件名带语言标签,会被覆盖吗?**
不会。主名一致时保留语言标签(`Movie.chs.srt`、`Movie.zh.srt` 互不覆盖)。

**Q: 令牌在哪里?**
`data/api-token` 文件,或启动日志;也可用环境变量 `API_TOKEN` 固定。

**Q: 想改端口?**
编辑 `docker-compose.yml` 的 `ports: "8000:8000"` 左侧改为你想要的端口,然后 `docker compose up -d`。

---

## 八、本地开发与测试

```bash
# 安装依赖(需要 Python 3.10+)
pip install -r requirements.txt

# 启动(本地调试,端口 8001)
MEDIA_DIR=/tmp/subhub-e2e/media DATA_DIR=/tmp/subhub-e2e/data \
  python3 -m uvicorn app.main:app --port 8001

# 运行全部单元测试
python3 -m unittest discover -s tests -v
```

测试覆盖:STRM 解析与落位、字幕保存(zip/7z 解包)、zimuku 验证码放行与解析、OpenSubtitles 网页版(FlareSolverr)解析与下载、各 API 源解析。

---

## 九、项目结构

```text
subhub/
├── app/
│   ├── main.py                 # FastAPI 入口与路由
│   ├── config.py               # 环境变量配置
│   ├── models.py               # API 数据模型
│   ├── version.py
│   ├── providers/
│   │   ├── base.py             # Provider 抽象基类
│   │   ├── zimuku.py           # 字幕库网页源(自动过验证码 + 7z 解压)
│   │   ├── subhd.py            # SubHD 网页源
│   │   ├── assrt.py            # assrt API 源
│   │   ├── opensubtitles.py    # OpenSubtitles API 源
│   │   ├── opensubtitles_web.py# OpenSubtitles 网页版(FlareSolverr)
│   │   └── save.py             # 字幕保存与 zip/7z 解包
│   ├── services/
│   │   ├── media_library.py    # 扫描、标题/封面识别、strm、字幕落位
│   │   └── store.py            # SQLite 持久化
│   └── static/                 # 前端单页(index.html / app.js / styles.css)
├── tests/
│   ├── test_subhub.py          # STRM / 落位 / 保存 / 各 API 源测试
│   ├── test_new_providers.py   # zimuku / 7z / OpenSubtitles 网页版测试
│   └── fixtures/               # 真实页面样本
├── Dockerfile                  # 镜像构建(非 root 运行)
├── docker-compose.yml          # 一键部署编排
├── requirements.txt
└── README.md
```

---

## 版本记录

| 版本 | 日期 | 更新内容 |
| --- | --- | --- |
| v0.2.0 | 2026-09-24 | 字幕源对齐:新增 zimuku(自动过验证码)与 OpenSubtitles 网页版(FlareSolverr),共 5 源;7z 解压支持;不包含成人内容源 |
| v0.1.0 | 2026-09-24 | 首个版本:媒体库扫描 + STRM 支持 + SubHD/assrt/OpenSubtitles 三源 + 前端 + Docker |

---

## 免责声明

本项目仅供个人学习与自用媒体管理。请遵守字幕源网站的服务条款与相关法律法规,合理使用。
