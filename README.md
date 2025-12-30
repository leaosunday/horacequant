# HoraceQuant

一个面向 A 股的个人量化项目：提供 **行情数据入库（日/周 K）**、**通达信（TDX）公式选股**、以及 **FastAPI 后端接口**供前端展示（K 线 + 指标 + 选股结果流式加载）。

本文档面向“可运行、可迭代、可上线”的工程化使用方式，尽量覆盖：
- 项目结构与职责边界
- 本地开发与部署方式
- 数据入库与选股流程
- 配置项（环境变量）
- 常见问题排查

---

## 目录结构

```
horacequant/
  backend/                  # 后端与运维脚本（Python）
    app/                    # FastAPI 应用代码
    ops/scripts/            # 运维脚本：入库、选股
    rules/                  # 选股策略（TDX 公式文件）
    logs/                   # 运行日志（默认）
    requirements.txt        # Python 依赖
    run.py                  # 启动 FastAPI
    worker.py               # 启动定时任务 Worker（APScheduler）
  frontend/                 # 前端（Vue3 + Vite）
  README.md
```

---

## 环境准备

### 后端（Python）

- Python 版本建议：3.10+（推荐 3.11+）
- PostgreSQL：12+（建议 14+）
- 依赖安装（推荐在虚拟环境/conda env 里执行）：

```bash
pip install -r backend/requirements.txt
```

> 备注：仓库依赖包含 `psycopg2-binary`（用于 ops 脚本）与 `asyncpg`（用于 FastAPI）。

### 前端（Node.js）

- Node.js 建议：18+（Vite 7 / Vue 3）
- 安装依赖：

```bash
cd frontend
npm install
```

---

## 快速开始（本地开发）

### 1) 启动后端 API（FastAPI）

```bash
python backend/run.py
```

默认监听：`0.0.0.0:8000`（可通过环境变量配置）。

### 2) 启动前端（Vite）

前端默认端口：`5173`，并已在 `frontend/vite.config.ts` 配置了代理：
`/api -> http://127.0.0.1:8000`，便于本地联调。

```bash
cd frontend
npm run dev
```

### 3) 启动定时任务 Worker（可选，但推荐）

Worker 负责每日定时：入库 + 选股（可配置策略列表）。

```bash
python backend/worker.py
```

---

## 后端 API 概览

### 基础接口

- `GET /api/v1/hello`：连通性测试
- `GET /api/v1/healthz`：健康检查（含 DB）

### 选股与图表数据（核心）

- `GET /api/v1/picks/{rule_name}/{trade_date}`
  - 返回 JSON（带统一 `ApiResponse` 包裹）
  - 支持 `cursor` 分页（每页 `limit <= 50`）
  - 参数示例：`trade_date` 支持 `YYYY-MM-DD` 或 `YYYYMMDD`

- `GET /api/v1/picks/{rule_name}/{trade_date}/stream`
  - 返回 NDJSON（流式）
  - 第一条为 `meta`，后续为 `item`
  - 适合前端“下拉加载/边拉边画”

> 说明：当某日结果表不存在时（例如还没跑出选股结果），接口会返回空列表而不是 404，方便前端做“等待数据生成”的体验。

---

## 数据与选股流程

### 1) 入库：A 股日 K（近两年）

脚本：`backend/ops/scripts/a_share_daily_to_postgres.py`

- 数据源：AkShare `stock_zh_a_hist(period="daily")`
- 目标表：`stock_basic`、`stock_daily`

示例：

```bash
export PG_HOST=127.0.0.1
export PG_PORT=5432
export PG_USER=你的用户名
export PG_PASSWORD=你的密码  # 可为空（本机免密）
export PG_DB=horace_quant

python backend/ops/scripts/a_share_daily_to_postgres.py --adjust qfq
```

### 2) 入库：A 股周 K（近两年）

脚本：`backend/ops/scripts/a_share_weekly_to_postgres.py`

- 数据源：AkShare `stock_zh_a_hist(period="weekly")`
- 目标表：`stock_weekly`
- 特别处理：同一周内重复写入时，会删除旧的“本周旧数据”，避免周线重复/不一致

```bash
python backend/ops/scripts/a_share_weekly_to_postgres.py --adjust qfq
```

### 3) 选股：TDX 公式（示例 b1）

脚本：`backend/ops/scripts/stock_picker_tdx.py`

- 输入：`backend/rules/*.tdx`
- 输出：按交易日分表 `stock_pick_results_YYYYMMDD`

```bash
python backend/ops/scripts/stock_picker_tdx.py --rule backend/rules/b1.tdx --rule-name b1 --trade-date 2025-12-29
```

> 重要：本项目的 TDX 解析器实现了覆盖 `b1.tdx` 所需的子集（`LLV/HHV/SMA/EMA/MA/REF/INBLOCK/NAMELIKE` 等）。

---

## 指标与缓存（性能策略）

为了避免前端每次拉取都实时计算大量指标，后端采用“按需计算 + DB 回填”的方式：

- 指标缓存表：
  - `stock_daily_indicators`
  - `stock_weekly_indicators`
- 市值缓存表：
  - `stock_market_cap_latest`

当 API 发现某个交易日指标缺失时，会：
1) 拉取 K 线（含历史窗口）
2) 计算指标（MACD / KDJ / ZX Short / ZX Long 等）
3) 只回填缺失行（逐行缺失判断）

---

## 定时任务 Worker（每日流水线）

Worker（`backend/worker.py`）内部使用 APScheduler，默认在 **Asia/Shanghai 16:00** 触发：

1) 当日日 K 入库
2) 周 K 更新（含“同周覆盖”）
3) 遍历策略列表执行选股（目前默认 `b1`）

并使用 PostgreSQL advisory lock 防止多实例重复执行。

---

## 配置（环境变量）

### 后端（FastAPI / Worker）

后端使用 `HQ_` 前缀（见 `backend/app/core/config.py`），常用项：

- **运行环境**
  - `HQ_ENV=dev|staging|prod`
  - `HQ_HOST=0.0.0.0`
  - `HQ_PORT=8000`
  - `HQ_LOG_LEVEL=INFO`
  - `HQ_LOG_DIR=backend/logs`

- **PostgreSQL**
  - `HQ_PG_HOST=127.0.0.1`
  - `HQ_PG_PORT=5432`
  - `HQ_PG_USER=...`
  - `HQ_PG_PASSWORD=...`
  - `HQ_PG_DB=horace_quant`

- **CORS（前端联调）**
  - `HQ_CORS_ENABLED=true`
  - `HQ_CORS_ALLOW_ORIGINS=http://127.0.0.1:5173,http://localhost:5173`

- **定时任务**
  - `HQ_SCHEDULER_ENABLED=true|false`
  - `HQ_SCHEDULER_TIMEZONE=Asia/Shanghai`
  - `HQ_SCHEDULER_HOUR=16`
  - `HQ_SCHEDULER_MINUTE=0`
  - `HQ_SCHEDULER_LOCK_KEY=42424242`
  - `HQ_STRATEGIES=b1,b2`（策略列表，逗号分隔或 JSON 数组）

> 建议：生产部署中 **API 进程与 Worker 进程分开运行**。通常做法是：
> - API：`HQ_SCHEDULER_ENABLED=false`
> - Worker：`HQ_SCHEDULER_ENABLED=true`

### 运维脚本（入库/选股）

运维脚本使用 `PG_` 前缀：

- `PG_HOST / PG_PORT / PG_USER / PG_PASSWORD / PG_DB`

---

## 日志

默认输出到 `backend/logs/`，并按类型拆分（按天滚动、自动清理）：

- `app.log`：业务日志
- `jobs.log`：定时任务日志（含 worker）
- `access.log`：HTTP access
- `error.log`：ERROR 汇总

---

## 常见问题排查

### 1) /api/v1/picks 返回空列表

可能原因：
- 当天选股结果表尚未生成（还没跑选股脚本/worker）

建议：
- 检查 `backend/logs/jobs.log`
- 手动执行一次：
  - `python backend/ops/scripts/stock_picker_tdx.py --rule backend/rules/b1.tdx --rule-name b1 --trade-date YYYY-MM-DD`

### 2) KDJ/RSV 等指标全是 NaN 导致漏选

通达信 SMA 是递推型指标，若初始值为 NaN 容易污染整条链路。
项目已在 `stock_picker_tdx.py` 中按 TDX 语义处理 NaN（启动值与断档回填），若你新增策略时仍遇到类似问题，建议优先检查：
- 分母为 0 导致 `inf/-inf`
- 数据窗口长度不足
- 某些列缺失或类型不是数值

### 3) AkShare 拉数失败或返回空

检查网络与 AkShare 数据源可用性，并查看脚本/worker 日志中的报错堆栈。

---

## 许可证

个人项目，默认不提供任何商业保证。如需开源协议可再补充。