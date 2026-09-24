# SubHub — 媒体库字幕搜索与下载工具

> 🎬 一键为你的 Jellyfin / Emby / Plex 媒体库(含 **STRM 虚拟文件**)自动搜索并下载字幕,字幕自动落到媒体同目录,播放器直接识别。
> 🐳 已发布到 Docker Hub:**`marsjimmyliu/subhub`**,两条命令即可跑起来,无需懂代码、无需构建。

---

## 目录

- [SubHub 是什么?](#subhub-是什么)
- [功能特性](#功能特性)
- [支持的 5 个字幕源](#支持的-5-个字幕源)
- [一、快速上手:直接拉取 Docker 镜像](#一快速上手直接拉取-docker-镜像)
- [二、详细安装:docker compose(推荐)](#二详细安装docker-compose推荐)
- [三、NAS 安装指南(群晖 / 威联通 / 通用)](#三nas-安装指南群晖--威联通--通用)
- [四、打开网页开始使用](#四打开网页开始使用)
- [五、字幕源配置详解](#五字幕源配置详解)
- [六、STRM 虚拟文件支持](#六strm-虚拟文件支持)
- [七、安装后的调试与设置](#七安装后的调试与设置)
- [八、常用环境变量](#八常用环境变量)
- [九、对外 API(进阶)](#九对外-api进阶)
- [十、常见问题(FAQ)](#十常见问题faq)
- [十一、本地开发与测试](#十一本地开发与测试)
- [十二、项目结构](#十二项目结构)
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
| 🐳 **双架构镜像** | 已发布 `linux/amd64` + `linux/arm64`,x86 与 ARM NAS 都能跑 |

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

## 一、快速上手:直接拉取 Docker 镜像

> 最快的方式:不需要下载源码、不需要构建,直接拉现成镜像。

**前提:已安装 Docker**(未安装请看下文"第 0 步")。

```bash
# 1. 建目录
mkdir -p subhub/media subhub/data && cd subhub

# 2. 拉镜像并启动
docker run -d --name subhub --restart unless-stopped \
  -p 8000:8000 \
  -v "$PWD/media:/media:rw" \
  -v "$PWD/data:/data" \
  marsjimmyliu/subhub:latest

# 3. 打开网页
#   http://localhost:8000
```

> 想在别的端口访问?把 `-p 8000:8000` 改成 `-p 9000:8000`(左侧是访问端口)。

**第 0 步:安装 Docker**

- **Windows**:安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)(安装后启动,若提示 WSL2 按提示启用并重启)。
- **macOS**:同样安装 Docker Desktop。
- **Linux(Ubuntu/Debian)**:
  ```bash
  sudo apt update
  sudo apt install -y docker.io docker-compose-plugin
  sudo systemctl enable --now docker
  ```
- 验证:`docker --version` 能输出版本号即可。

---

## 二、详细安装:docker compose(推荐)

Compose 方式适合想要自定义端口、环境变量、目录映射的场景,后续升级也最方便。

### 第 1 步:下载项目文件

```bash
git clone https://github.com/marsjimmy/subhub.git
cd subhub
```

> 不会用 git?点击 GitHub 页面 **Code → Download ZIP**,解压后进入文件夹。只需要其中的 `docker-compose.yml`,也可以自己新建一个同名的空文件照抄下面的内容。

### 第 2 步:创建数据目录

```bash
mkdir -p media data
```

- `media/`:放你的媒体文件或 strm 文件(或把整个媒体库目录映射进来,见下文);
- `data/`:存放数据库、API 令牌、无媒体场景下下载的字幕。

### 第 3 步:启动(直接拉镜像,无需构建)

```bash
docker compose up -d
```

> 项目自带的 `docker-compose.yml` 已默认使用 Docker Hub 镜像 `marsjimmyliu/subhub:latest`。首次拉取约 256MB,取决于网络 1~5 分钟。看到 `Started` 或 `done` 即成功。

### 第 4 步:验证

```bash
docker compose ps          # 状态应为 Up
docker logs subhub         # 日志无报错
```

然后浏览器访问 <http://localhost:8000>。

### 目录映射说明(重要)

| 宿主机目录 | 容器目录 | 权限 | 用途 |
| --- | --- | --- | --- |
| `./media` | `/media` | 读写 | 视频 / strm 文件与本地封面(**strm 场景必须 rw**,需写入字幕) |
| `./data` | `/data` | 读写 | SQLite 数据库、API 令牌、下载的字幕 |

**把媒体库目录换成你自己的**:编辑 `docker-compose.yml`,把 `./media:/media:rw` 改成你的真实路径,例如:

```yaml
volumes:
  - /volume1/video:/media:rw      # 群晖共享文件夹示例
  - ./data:/data
```

> 只读场景(如网盘挂载只读):可改成 `:ro`,SubHub 会自动把字幕存到 `data/downloads/` 并在界面提示。

### 修改端口

编辑 `docker-compose.yml`:

```yaml
ports:
  - "9000:8000"     # 左侧 9000 是访问端口,右侧 8000 是容器端口(勿改)
```

改完执行 `docker compose up -d` 生效。

### 固定 API 令牌(可选)

```yaml
environment:
  API_TOKEN: "换成你的高强度随机字符串"
```

---

## 三、NAS 安装指南(群晖 / 威联通 / 通用)

NAS 上安装分两种:图形界面(适合新手)和 SSH 命令行(通用)。本镜像同时支持 x86 与 ARM 架构,常见 NAS 均可运行。

### 方式 A:群晖 Synology(DSM 7.2+,图形界面)

1. 打开 **套件中心**,安装 **Container Manager**(旧版叫 Docker);
2. 打开 Container Manager → **注册表** → 搜索框输入 `marsjimmyliu/subhub` → 选中镜像 → **下载**(选择 `latest` 标签);
3. 下载完成后进入 **映像** → 选中 `marsjimmyliu/subhub` → **运行**:
   - **常规设置**:容器名随意(如 `subhub`),勾选"启用自动重新启动";
   - **高级设置 → 端口设置**:本地端口 `8000` → 容器端口 `8000`(本地端口可改,如 NAS 已占用就换 `9000`);
   - **高级设置 → 卷**:添加文件夹
     - 共享文件夹(如 `docker/subhub/media`)→ 装载路径 `/media`,勾选读写;
     - 共享文件夹(如 `docker/subhub/data`)→ 装载路径 `/data`,勾选读写;
   - **高级设置 → 环境**:可添加 `API_TOKEN`(可选);
4. 点击 **应用/保存** 启动容器;
5. 浏览器访问 `http://<NAS的IP>:8000`。

> 找不到注册表?先确认 NAS 能访问外网,或在"注册表"右上角设置里换镜像源。

### 方式 B:威联通 QNAP(Container Station)

1. 打开 **App Center**,安装 **Container Station**;
2. Container Station → **映像** → **提取**(Pull)→ 输入 `marsjimmyliu/subhub:latest` → 提取;
3. 在映像列表选中它 → **创建容器**:
   - **端口**:主机 `8000` → 容器 `8000`;
   - **卷**:添加两个映射:`/media`(对应你的影片共享文件夹)与 `/data`(对应数据文件夹),均读写;
   - **重启策略**:选择"始终重启";
4. 启动后访问 `http://<NAS的IP>:8000`。

### 方式 C:通用 NAS(绿联 / 极空间 / 铁威马 / 飞牛fnOS / 其他)——SSH + docker compose

绝大多数 NAS 都支持 SSH,步骤完全一致:

1. **开启 SSH**:NAS 控制面板 → 终端机/SSH → 启用(默认端口 22,设置强密码);
2. 用电脑的终端 SSH 登录:`ssh 用户名@NAS的IP`;
3. 依次执行:

```bash
mkdir -p /volume1/docker/subhub/media /volume1/docker/subhub/data
cd /volume1/docker/subhub
# 创建 compose 文件(内容见下方,路径按你的 NAS 改)
vim docker-compose.yml
docker compose up -d
```

`docker-compose.yml` 内容(NAS 版,改好路径):

```yaml
services:
  subhub:
    image: marsjimmyliu/subhub:latest
    container_name: subhub
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - /volume1/video:/media:rw       # 改成你的影片共享文件夹
      - /volume1/docker/subhub/data:/data
    shm_size: "1gb"
```

> 不会 vim?用 `nano docker-compose.yml`;或直接在电脑上写好文件,用 WinSCP / 群晖 File Station 上传到 NAS。

4. 访问 `http://<NAS的IP>:8000`。

### NAS 安装后必查的 3 件事

1. **目录权限**:容器内以 `uid=1000` 的非 root 用户运行。若容器内写不了 `media/`(报权限错误),在 NAS 上执行:
   ```bash
   sudo chown -R 1000:1000 /volume1/docker/subhub/data
   sudo chmod -R 777 /volume1/video        # 或只对字幕写入目录授权
   ```
2. **防火墙/端口**:NAS 防火墙若开启,放行 `8000` 端口;否则局域网外设备访问不到。
3. **局域网访问**:用 NAS 的 IP 而不是 `localhost`,如 `http://192.168.1.10:8000`。

---

## 四、打开网页开始使用

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

## 五、字幕源配置详解

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
docker run -d --name flaresolverr --restart unless-stopped \
  -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest
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

## 六、STRM 虚拟文件支持

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

## 七、安装后的调试与设置

装好后按下面的清单走一遍,10 分钟确认一切正常。

### 1. 确认服务正常

```bash
docker compose ps        # 状态为 Up
docker logs subhub       # 无 ERROR 报错
curl http://localhost:8000/api/health   # 返回 {"status":"ok"}
```

### 2. 第一次打开界面

浏览器访问 `http://localhost:8000`(NAS 用 `http://NAS的IP:8000`)。看到"媒体"页面即正常。
- 页面不需要登录;只有调用 API 才需要 Bearer Token(存在 `data/api-token`,首次启动自动生成)。

### 3. 设置字幕源(设置页)

1. 确认 **字幕库(zimuku)**、**SubHD** 已勾选(默认开启);
2. 想用 assrt → 填 Token;想用 OpenSubtitles 网页版 → 填 FlareSolverr 地址;想用官方 API → 填三件套;
3. 至少保留一个开启的源,否则搜索会提示"请先在设置中开启至少一个字幕源"。

### 4. 测试一次完整流程

1. **媒体页**:如果 `media/` 里有视频或 strm,应看到卡片;点击卡片 **搜索字幕**;
2. **字幕页**:也可以手动输入片名搜索,如 `肖申克的救赎`;
3. 结果列表点 **下载**,按钮变为"已保存";
4. **验证落位**:
   ```bash
   ls media/                 # 应出现 Movie.srt / Movie.ass 等文件
   head -5 media/Movie.srt   # 能看到字幕时间轴内容
   ```

### 5. 常见问题排查速查

| 现象 | 排查 |
| --- | --- |
| 网页打不开 | `docker compose ps` 是否 Up;防火墙是否放行端口;NAS 用 IP 访问 |
| 搜索无结果 | 设置页至少开启一个源;网站反爬波动,稍后重试 |
| zimuku 报"验证码放行失败" | 网站验证码升级,稍后重试;可先关闭该源 |
| FlareSolverr 报错 | 确认容器运行、地址正确(局域网填 IP 不填 localhost) |
| 字幕写不进 media | 目录只读或权限不足:检查挂载为 `:rw`,NAS 上 `chown -R 1000:1000` |
| 日志在哪看 | `docker compose logs -f` 实时查看 |

---

## 八、常用环境变量

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

## 九、对外 API(进阶)

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

## 十、常见问题(FAQ)

**Q: 网页打不开?**
检查容器是否运行:`docker compose ps`。若状态不是 `Up`,查看日志:`docker compose logs -f`。NAS 请用 `http://NAS的IP:8000` 访问,并确认防火墙放行端口。

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

**Q: NAS 上容器写不进目录?**
容器以 uid 1000 运行,执行 `sudo chown -R 1000:1000 <目录>` 或 `sudo chmod -R 777 <目录>`。

**Q: 镜像拉取很慢/失败?**
国内网络可配置 Docker 镜像加速器(各 NAS 与 Docker Desktop 设置中都有"镜像加速"入口,如填入 `https://docker.m.daocloud.io` 等)。

---

## 十一、本地开发与测试

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

## 十二、项目结构

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
├── .github/workflows/          # 自动构建并推送 Docker Hub 的 CI
├── Dockerfile                  # 镜像构建(非 root 运行)
├── docker-compose.yml          # 一键部署编排(默认拉取 Docker Hub 镜像)
├── requirements.txt
└── README.md
```

---

## 版本记录

| 版本 | 日期 | 更新内容 |
| --- | --- | --- |
| v0.2.0 | 2026-09-24 | 字幕源对齐 5 源;STRM 支持;发布 Docker Hub(`marsjimmyliu/subhub`);自动构建 CI;详细安装教程(NAS / Compose / 调试) |
| v0.1.0 | 2026-09-24 | 首个版本:媒体库扫描 + STRM 支持 + SubHD/assrt/OpenSubtitles 三源 + 前端 + Docker |

---

## 免责声明

本项目仅供个人学习与自用媒体管理。请遵守字幕源网站的服务条款与相关法律法规,合理使用。
