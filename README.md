# 白泽公考 (BaizeGK)

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0.html)

> 铜仁与重庆个人备考：查看招录状态、按地区与卷别做限时练习、回查作答、保存申论、筛选职位表。无需联网模型；复盘材料可由你决定是否复制到如意。

## 本机使用（Windows PowerShell）

首次安装和每次更新后构建前端：

```powershell
Set-Location D:/code/BaizeGK
uv venv backend/.venv
uv pip install --python backend/.venv/Scripts/python.exe -r backend/requirements.txt
Set-Location frontend
npm ci
npm run build
```

日常启动（首次建本地库，以后自动复用）：

```powershell
Set-Location D:/code/BaizeGK/backend
./.venv/Scripts/python.exe run_local.py
```

打开 **http://127.0.0.1:8765/**。只监听本机；终端保持打开，关闭用 Ctrl+C。换端口可加 `--port 8766`。个人工作台单独使用 `C:/data/BaizeGK/study.sqlite3`，不会读取或改写旧的 `backend/gongkao.db`，也没有迁移旧作答。测试时用 `--db D:/tmp/BaizeGK-test/study.sqlite3 --port 18766` 指定独立库；不要用日常库做测试。

- **公告**：点「更新核验」，按官方正文填写本轮时间。没有查到公告、来源无法核验和已经确认是不同状态。2026 年参考数据不会参与当前撞期判断。该版本面向 2027 年度；下一年度需更新配置和历史参考。不自动抓取或报名。
- **试卷与申论**：从地区卡点「练对应试卷」，可先下载带有「非真题」标签的 JSON 示例。按示例整理自己有权用的资料并导入。真实个人资料使用 `kind: "user_material"`；确实核对过的答案才用 `answer_status: "verified"`。待核对题不携带参考答案；如要修订试卷，另用新 `id`，原卷和历史保留。用时从题目首次打开到提交，未提交题不计入正确率。申论可保存和回查；支持复制材料对照点评提示词，产品没有配置模型，不自动发送。
- **职位表**：从官方公告下载 XLS、XLSX 或 CSV，再填公告和附件原地址。贵州 2026 年度官方表可从铜仁网公告的「附件 2」二维码下载原 XLS，不用转格式。该表按大专、本科、研究生分别列专业，并保留定向招录的条件。历史表和测试表不会显示为可报名。导入后可查工作表和原行；年龄和专业筛选只用于初筛，不替代公告和招录机关解释。遇到非标准列名，请先保留原件，另存带「职位名称」「学历」「专业」等表头的副本，并保留行位置。

## 技术栈

| 层 | 选型 |
| --- | --- |
| 后端 | FastAPI |
| 前端 | Vue 3 + Vite |
| ORM | SQLModel（基于 SQLAlchemy + Pydantic） |
| 日志 | loguru |
| 配置 | YAML（config.yaml） |
| 数据库 | 开发期 SQLite，可平滑切 PostgreSQL / MySQL |

## 目录结构

```
BaizeGK/
├── backend/              # FastAPI 后端
│   ├── app/
│   │   ├── main.py       # 应用入口（lifespan + CORS + 路由）
│   │   ├── config.py     # 读取 config.yaml
│   │   ├── logging_conf.py  # loguru 配置（控制台 + 文件滚动）
│   │   ├── database.py   # SQLModel 引擎与会话
│   │   ├── models.py     # SQLModel 模型（User / Question）
│   │   ├── schemas.py    # 首页响应模型
│   │   └── routers/
│   │       └── home.py   # /api/home 首页数据接口
│   ├── config.yaml       # 配置中心
│   ├── requirements.txt
│   └── run.py            # 开发启动入口
└── frontend/             # Vue 3 + Vite 前端
    ├── index.html
    ├── vite.config.js    # /api 代理到 8000
    └── src/
        ├── App.vue
        ├── main.js
        ├── style.css
        ├── api/home.js   # 首页数据请求
        └── components/Home.vue  # 首页
```

## 快速开始

### 后端

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# 访问 http://localhost:8000  docs: http://localhost:8000/docs
```

首页数据接口：`GET /api/home`

### 前端

```bash
cd frontend
npm install
npm run dev
# 访问 http://localhost:5173
```

前端通过 Vite 代理把 `/api` 转发到后端 `8000`，开发期无需处理跨域。

## 导入题库与运行回归测试

从 `backend` 目录执行：

```bash
python -m app.ingest --seed "<有权使用的资料目录>"
python -m unittest discover -s tests -v
```

默认增量去重。`--rebuild` 会额外校验输入覆盖已有真题，再补新题；缺少已入库题目时拒绝执行，不清空题库。保留现有题目 ID 和 `gongkao.db` 文件名，不迁移个人答题记录。测试只使用临时数据库和测试题。

## 首页数据

首页文案由后端 `/api/home` 下发，前端纯展示，便于后续接数据库 / CMS 动态化。

## 贡献

欢迎提交 Issue 与 Pull Request。提交前请确保后端可正常启动、`GET /api/home` 返回 200。

## 许可证

本项目基于 [GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE) 开源，Copyright (c) 2026 DaPengRuYi。

AGPL-3.0 是 GPL 家族中传染性最强的协议：任何使用本项目代码（包括通过网络以服务形式提供）的用户，都必须开放其完整对应源代码。本项目采用 AGPL-3.0，以确保任何基于本项目的衍生服务都保持开源、与社区共享。
