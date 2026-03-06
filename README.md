# Blog Project 后端（Django REST API）

> 面向博客系统的后端服务，提供认证、文章、分类、合集、评论、媒体库、日志审计与文档化 API。

---

## 👥 面向使用者（User Guide）

### 1) 这是什么

`blog_project` 是博客系统后端，主要能力：
- 用户认证（登录 / 登出 / Token）
- 文章管理（含 Markdown 内容）
- 分类、合集、评论管理
- 媒体文件管理（上传、浏览、重命名）
- OpenAPI 文档（Swagger / Redoc）

### 2) 技术栈（你会直接接触到的）

- Python `3.12`
- Django `4.2`
- Django REST Framework `3.15`
- MySQL `8.x`（`utf8mb4`）
- drf-spectacular（OpenAPI）
- WhiteNoise（静态资源）

### 3) 快速开始（本地）🚀

```bash
cd /home/pdnbplus/project/blog-project/blog_project
python3.12 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
make run
```

默认开发配置：`config.settings.dev`（见 `manage.py`）。

### 4) 常用命令

```bash
make install       # 安装依赖
make migrate       # makemigrations + migrate
make run           # 启动开发服务
make check         # Django 系统检查
make docs          # 生成 OpenAPI schema.yml
make lint          # ruff + mypy
make format        # black + ruff --fix
make test          # 全量测试
make unit-test     # 单元测试（--tag=unit）
make api-test      # 接口测试（--tag=api）
```

### 5) 接口与文档入口

- Django Admin：`/admin/`
- API 前缀：`/api/v1/`
- OpenAPI Schema：`/api/schema/`
- Swagger：`/api/docs/swagger/`
- Redoc：`/api/docs/redoc/`

### 6) 静态资源上传与归档规则（当前生效）🗂️

文章相关：
- 后端自动归档，不依赖前端手填 `source_markdown_path`。
- 文章保存时落盘：`<BASE_DIR>/static/temp/<分类层级>/<文章标题>.md`
- 文章封面上传落盘：`<BASE_DIR>/static/temp/<分类层级>/img/<文章标题>.<后缀>`
- `upload-markdown` / `upload-cover` 要求：必传 `title`，可选 `category`，禁止传 `source_markdown_path`。

合集封面：
- 仍通过 `/api/v1/admin/media/upload/`，`temp/uploads/collection-cover` 归一到 `temp/collection`。
- 文件名采用 `<合集名称>.<后缀>`，并支持 `overwrite=1` 覆盖同名文件。

说明：
- 若新建文章时仅填写 `cover_path` 为 `http/https` 链接且未上传本地封面文件，不会在本地保存图片，只记录数据库字段。

---

## 👨‍💻 面向开发者（Developer Guide）

### 1) 技术栈（完整）

- Runtime：Python `3.12`
- Web：Django `4.2` + DRF `3.15`
- DB：MySQL `8.x`（通过 `PyMySQL` 适配 MySQLdb）
- API 文档：drf-spectacular
- 跨域：django-cors-headers
- 静态文件：WhiteNoise
- 内容处理：markdown + bleach + pygments
- 质量工具：Ruff / Black / Mypy / django-stubs

### 2) 目录结构（工程视角）

```text
blog_project/
├── manage.py
├── Makefile
├── requirements.txt
├── .env.example
├── config/
│   ├── __init__.py          # PyMySQL install_as_MySQLdb
│   ├── urls.py
│   └── settings/
│       ├── base.py
│       ├── dev.py
│       ├── prod.py
│       ├── local.py
│       └── production.py
├── apps/
│   ├── common/              # 统一响应、异常、分页、审计日志等
│   ├── users/               # 认证与用户相关接口
│   └── articles/            # 文章/分类/合集/评论/媒体核心业务
├── scripts/                 # 数据迁移/导出辅助脚本
├── static/                  # 项目内静态资源 + temp 归档
├── media/                   # 兼容/运行时媒体目录
├── templates/
├── logs/
└── schema.yml
```

### 3) 与《Django后端开发规范》对齐评估 ✅

对照文件：`/home/pdnbplus/project/Django后端开发规范.md`

| 规范项 | 当前状态 | 说明 |
|---|---|---|
| Python 3.12 + Django 4.2 + DRF + MySQL | ✅ 已对齐 | 版本与架构一致 |
| 配置分层（base/dev/prod） | ✅ 已对齐 | `config/settings/*` 已分层 |
| 环境变量驱动 | ✅ 已对齐 | `.env` + `.env.example` |
| MySQL utf8mb4 + CONN_MAX_AGE | ✅ 已对齐 | `base.py` 数据库配置已实现 |
| PyMySQL 兼容注册 | ✅ 已对齐 | `config/__init__.py` |
| DRF 统一认证/权限/分页/schema | ✅ 已对齐 | `REST_FRAMEWORK` 集中配置 |
| OpenAPI/Swagger/Redoc | ✅ 已对齐 | `config/urls.py` 暴露文档入口 |
| 统一响应与异常处理 | ✅ 已对齐 | `apps.common.responses/exceptions` |
| 日志体系 | ✅ 已对齐 | 审计日志 + 业务日志；prod 增加文件 handler |
| 测试分层（unit/api） | ✅ 已对齐 | `--tag=unit/api` + 测试目录完整 |
| 自动化命令（工程脚手架） | ✅ 已对齐 | Makefile 覆盖常用开发动作 |

### 4) 当前工程化现状与可改进点 🔧

已具备：
- 配置分层、接口规范化、日志与审计、文档化 API、测试标签分层。

建议优先补齐：
- CI 流水线固化：PR 自动执行 `make lint && make test && make docs`。
- 发布前门禁：禁止未迁移的模型变更（检查 `makemigrations --check`）。
- 版本化发布清单：发布时记录 commit、迁移号、schema 变更。
- README 与部署文档联动校验：每次接口变更同步 `schema.yml` 与文档。

### 5) 推荐后续开发流程（可持续扩展）

1. 新需求立项
- 明确接口契约（请求/响应/错误码）并先更新 `schema.yml` 预期。

2. 代码实现
- 业务逻辑优先下沉到 `services.py`，View 仅做编排。
- 通用逻辑复用 `apps/common`，避免重复造轮子。

3. 测试补全
- 至少补一条成功路径 + 一条失败路径。
- 涉及权限、上传、状态流转时必须补 API 级用例。

4. 质量检查
- 提交前执行：`make format && make lint && make test`。

5. 文档与发布
- 执行 `make docs` 更新 OpenAPI。
- 更新 README 中“行为性规则”（尤其上传/归档/兼容策略）。

### 6) 常见开发任务速查

```bash
# 生成/应用迁移
make migrate

# 只跑 API 测试
make api-test

# 只跑单测
make unit-test

# 生成并检查文档
make docs

# 生成登录 token
python manage.py gentoken <username>

# 路径兼容迁移（历史数据）
python manage.py migrate_source_markdown_path_to_static_temp --dry-run
python manage.py migrate_source_markdown_path_to_static_temp
```

---

## 📦 部署与运维补充

- 命令行部署参考：`部署文档.md`
- 云服务器（复用现有 nginx/mysql）参考：
  - `/home/pdnbplus/云服务器配置文件/blog项目_前后端部署方案_复用现有nginx.md`

