# fi_earn — A 股量化交易研究平台

基于 **OpenBB Platform + AkShare + AKQuant + Streamlit** 构建的 A 股量化投研工具。

## 功能模块

| 页面 | 功能 |
|---|---|
| 首页 | 市场总览：涨跌幅榜单、主要指数、成交量 |
| 行情查询 | 股票搜索 + 交互式 K 线图 |
| 技术分析 | K 线图 + MA/MACD/RSI/BOLL 等指标叠加 |
| 策略回测 | 策略配置、AKQuant 回测引擎、收益/回撤可视化 |
| 因子研究 | 因子计算、IC 分析、分组回测 |

## 技术栈

- **数据**: [OpenBB Platform](https://github.com/OpenBB-finance/OpenBB) + [openbb-akshare](https://github.com/finanalyzer/openbb_akshare)（A 股免费数据）
- **回测**: [AKQuant](https://github.com/akfamily/akquant)（Rust 内核高性能回测）
- **UI**: [Streamlit](https://streamlit.io) 多页面看板
- **可视化**: [Plotly](https://plotly.com/python/)

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 首次安装后重建 OpenBB 资源（注册 akshare provider）
python -c "import openbb; openbb.build()"

# 3. 复制环境变量模板（可选）
cp .env.example .env

# 4. 启动 Web 看板
streamlit run app/Home.py
```

访问 http://localhost:8501 打开看板。

## 项目结构

```
fi_earn/
├── app/
│   ├── Home.py              # 首页：市场总览
│   └── pages/
│       ├── 1_行情查询.py
│       ├── 2_技术分析.py
│       ├── 3_策略回测.py
│       └── 4_因子研究.py
├── core/
│   ├── data/
│   │   ├── market.py        # 数据获取封装（OpenBB + AkShare）
│   │   └── cache.py         # 本地文件缓存
│   ├── strategy/
│   │   ├── base.py          # 策略基类
│   │   └── examples/        # 双均线、MACD 示例策略
│   └── backtest/
│       └── engine.py        # AKQuant 回测封装
├── notebooks/               # Jupyter 研究笔记
├── requirements.txt
├── .env.example
└── README.md
```

## 数据说明

本项目使用以下**完全免费**的数据源：

- **AkShare**：通过 openbb-akshare 插件接入，覆盖 A 股/港股实时与历史行情、财务数据、宏观经济数据
- **OpenBB Platform**：提供统一数据 API 接口，支持技术分析工具

无需注册，无需付费，开箱即用。
