# blog_project 后端（Django REST API）

本目录为博客系统后端服务，基于 Django 4.2 + DRF，提供认证、文章、分类、合集、评论、媒体库、统一错误处理与审计日志能力。

## 1. 技术栈

- Python 3.12
- Django 4.2
- Django REST Framework 3.15
- MySQL 8（utf8mb4）
- drf-spectacular（OpenAPI）
- django-cors-headers（跨域）
- WhiteNoise（静态文件）
- Ruff / Mypy / Black（代码质量）

## 2. 与《Django后端开发规范》对齐说明

本项目已对齐 `/home/pdnbplus/project/Django后端开发规范.md` 的核心要求：

- 配置分层：`config/settings/base.py` + `dev.py` + `prod.py`
- 环境变量驱动：`.env` / `.env.example`
- MySQL 8 + `utf8mb4` + 合理连接池参数（`DB_CONN_MAX_AGE`）
- DRF 统一认证、权限、分页、Schema 配置
- OpenAPI 文档入口（Schema / Swagger / Redoc）
- 统一响应结构与统一异常处理（`code/message/data`）
- 审计日志与错误日志落盘（中文消息便于排查）
- 测试分层：单元测试（`@tag("unit")`）+ 接口测试（`@tag("api")`）
- 自动化命令（Makefile）与类型检查（Mypy + django-stubs）

## 3. 目录结构（后端实际）

> 省略 `.git`、`.venv`、`__pycache__`、缓存与历史归档大文件。

```text
blog_project/
├── manage.py
├── Makefile
├── README.md
├── 部署文档.md
├── requirements.txt
├── pyproject.toml
├── mypy.ini
├── .env.example
├── schema.yml
├── config/
│   ├── urls.py
│   ├── asgi.py
│   ├── wsgi.py
│   └── settings/
│       ├── base.py
│       ├── dev.py
│       ├── local.py
│       ├── prod.py
│       └── production.py
├── apps/
│   ├── common/
│   ├── users/
│   └── articles/
├── scripts/
├── data/
│   ├── legacy/
│   └── recovery/
├── static/
├── media/
├── templates/
├── staticfiles/
└── logs/
```

## 4. 快速开始（本地开发）

### 4.1 环境准备

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4.2 配置环境变量

```bash
cp .env.example .env
```

`.env` 关键项：

- Django
  - `DJANGO_SECRET_KEY`
  - `DJANGO_DEBUG`
  - `DJANGO_ALLOWED_HOSTS`
- MySQL
  - `DB_HOST`
  - `DB_PORT`
  - `DB_NAME`
  - `DB_USER`
  - `DB_PASSWORD`
  - `DB_CONN_MAX_AGE`
- CORS
  - `CORS_ALLOWED_ORIGINS`
  - `CORS_ALLOWED_ORIGIN_REGEXES`

> 当前默认示例支持 `127.0.0.1` 与 `localhost` 的任意端口。

### 4.3 初始化并启动

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8001
```

默认开发配置为 `config.settings.dev`（见 `manage.py`）。

## 5. 常用命令（Makefile）

```bash
make install        # 安装依赖
make migrate        # makemigrations + migrate
make run            # 启动开发服务
make check          # Django 系统检查
make docs           # 生成 OpenAPI schema.yml
make lint           # ruff + mypy
make format         # black + ruff --fix
make collectstatic  # 收集静态文件
```

常用管理命令：

```bash
python manage.py gentoken <username>   # 生成或刷新用户 Token
```

## 6. 测试规范与执行

### 6.1 测试分层约定

- 单元测试（`@tag("unit")`）
  - 目标：纯函数/服务逻辑/序列化转换
  - 推荐基类：`SimpleTestCase`（无数据库）或 `TestCase`（有 ORM）
- 接口测试（`@tag("api")`）
  - 目标：认证鉴权、权限、参数校验、响应结构
  - 推荐基类：`APITestCase`

### 6.2 必测要点

- 成功路径 + 失败路径（未授权/无权限/参数错误）
- 状态码 + 统一响应体（`code/message/data`）
- 鉴权接口：登录、Token 生效、Token 失效

### 6.3 执行命令

```bash
make test           # 全量测试
make unit-test      # 仅单元测试
make api-test       # 仅接口测试

# 或
python manage.py test --tag=unit
python manage.py test --tag=api
```

## 7. API 与文档入口

- 后台：`/admin/`
- API 前缀：`/api/v1/`
- 认证：
  - `POST /api/v1/auth/login/`
  - `POST /api/v1/auth/logout/`
  - `GET /api/v1/auth/profile/`
- 内容：
  - `GET /api/v1/home/summary/`
  - `GET /api/v1/home/recommendations/`
  - `GET /api/v1/articles/`
  - `GET /api/v1/categories/`
  - `GET /api/v1/collections/`
- 管理端：
  - `/api/v1/admin/articles/`
  - `/api/v1/admin/categories/`
  - `/api/v1/admin/collections/`
  - `/api/v1/admin/comments/`
  - `/api/v1/admin/media/*`
  - `/api/v1/admin/logs/`
- OpenAPI：
  - `GET /api/schema/`
  - `GET /api/docs/swagger/`
  - `GET /api/docs/redoc/`

## 8. 错误处理与日志

- 统一异常处理：`apps.common.exceptions.custom_exception_handler`
- 统一响应封装：`apps.common.responses`
- 审计中间件：`apps.common.middleware.ApiAuditLogMiddleware`
- 日志工具：`apps.common.logging_utils`
- 日志文件：
  - `logs/blog_api.log`
  - `logs/blog_api_error.log`

## 9. 历史数据与兼容迁移

### 9.1 MySQL 8 初始化

```bash
python scripts/setup_mysql8.py
```

### 9.2 旧库导入

```bash
python manage.py import_legacy_data
# 或
python scripts/migrate_legacy_without_html.py
```

按需覆盖旧库参数（不依赖 `.env`）：

```bash
python manage.py import_legacy_data \
  --host 127.0.0.1 \
  --port 3306 \
  --user root \
  --password your_password \
  --database blog_project \
  --legacy-media-root /path/to/legacy/static/temp \
  --article-temp-root /path/to/project/static/temp
```

### 9.3 `source_markdown_path` 路径收敛

`/media/articles` 已弃用，统一到 `/static/temp/...`：

```bash
python manage.py migrate_source_markdown_path_to_static_temp --dry-run
python manage.py migrate_source_markdown_path_to_static_temp
```

## 10. 静态资源上传归档规范（2026-03）

### 10.1 文章（新建/编辑页）

- 前端不再要求或允许手填 `source_markdown_path`，归档路径由后端按“分类层级 + 文章标题”自动计算。
- 文章保存（创建/更新）时，后端会将正文落盘到：
  - `<BASE_DIR>/static/temp/<分类层级>/<文章标题>.md`
- 文章封面上传接口 `POST /api/v1/admin/articles/upload-cover/` 归档到：
  - `<BASE_DIR>/static/temp/<分类层级>/img/<文章标题>.<图片后缀>`
- 文章 Markdown 上传接口 `POST /api/v1/admin/articles/upload-markdown/` 归档到：
  - `<BASE_DIR>/static/temp/<分类层级>/<文章标题>.md`
- `upload-markdown` / `upload-cover` 入参要求：
  - 必传 `title`，可选 `category`
  - 禁止传 `source_markdown_path`，传入会返回 `400`
- 新版文章编辑器采用“选完文件，点击发布再统一上传”的流程：
  - Markdown：前端先本地读取，发布时由文章保存动作统一落盘。
  - 封面：发布前调用 `upload-cover` 上传，成功后再提交文章数据。
- 若新建文章时仅在“封面路径”输入链接（`http/https`）且未选择本地图片文件，则不会在本地保存图片，只会保存数据库字段 `cover_path`。

### 10.2 合集封面

- 合集封面仍走 `POST /api/v1/admin/media/upload/`，路径归一化规则保持不变：
  - `temp/uploads/collection-cover` => `temp/collection`
- 约定文件命名为 `<合集名称>.<后缀>`，并使用 `overwrite=1` 覆盖同名文件（修改图片直接覆盖）。
- 实际落盘：
  - `<BASE_DIR>/static/temp/collection/<合集名称>.<后缀>`

### 10.3 分类与媒体库

- 分类图标上传（`icon_file`）与媒体库常规上传行为保持不变。
- 媒体库上传接口新增可选参数：
  - `filename`：指定保存文件名（默认仍为上传文件原名）
  - `overwrite`：`1/true` 时覆盖同名文件（默认关闭，保持“重名自动加后缀”）

### 10.4 当前落地情况摘要

- 已实现：文章自动归档、封面归档、合集封面固定命名覆盖。
- 已保持不变：分类图标上传路径规则、媒体库默认上传行为。
- 现状说明：
  - `Article.source_markdown_path` 字段仍保留，但由后端归档流程统一生成并回填，不依赖前端传值。
  - `/api/v1/admin/articles/resolve-local-images/` 仍为 no-op，不会把本地引用图片落盘。

## 11. 生产运行与部署

- 生产 settings：`config.settings.prod`
- 建议流程：`migrate` -> `collectstatic` -> Gunicorn -> Nginx
- 详细命令版部署流程见：`部署文档.md`

## 12. 兼容说明

- 当前生效配置入口为 `config/*`。
- `blog_project/settings.py` 仅作历史兼容入口，不建议新代码继续依赖。
