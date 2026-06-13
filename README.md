# AShareAgents

> 🤖 面向中国 A 股市场的多智能体（Multi-Agent）投研与决策辅助平台。

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-sa/4.0/)

AShareAgents 基于现代 Agent 架构设计，融合 Multi-Agent 协同、RAG（检索增强生成）、长期记忆、上下文工程、金融知识库与工作流编排等核心能力，实现对市场、行业、公司、财报、新闻、公告、风险以及量化数据的自动化分析与研究，帮助用户构建真正具备自主研究能力的 AI 投研系统。
## 🚀 快速开始

### 项目安装
1. 克隆 AShareAgents：
```bash
git clone https://github.com/EPxiaoma/AShareAgents.git
```
2. 进入项目目录：
```bash
cd TradingAgents
```
3. 创建虚拟环境（以 uv 为例）：
```bash
uv venv
```
4. 激活环境：
```bash
# Windows:
.venv\Scripts\activate

# macOS / Linux:
source .venv/bin/activate
```
5. 安装包及其依赖项：
```bash
uv pip install -e .
```

### 环境配置
创建 `.env` 文件：
```bash
cp .env.example .env
```
最少提供一个模型 API KEY。 建议配置多个模型 API KEY，前端可以根据需求进行选择。

### 项目启动
```bash
streamlit run frontend/app.py
```

### 支持的 LLM 提供商

| 提供商类型   | 示例服务                               | 配置示例                             |
| ------------ | -------------------------------------- | ------------------------------------ |
| | |     |
||                  |  |
| |                |        |

## 🏗️ 项目结构
```
AShareAgents/
├── app/              
│   ├── api/                      # FastAPI API层
│   ├── LLM/                      # 大模型管理
│   ├── agents/                   # Agent 实现
│   ├── tools/                    # 工具系统
│   ├── context/                  # 上下文工程
│   ├── memory/                   # 记忆系统
│   ├── rag/                      # RAG 系统
│   └── skills/                   # Skills 系统
├── frontend/                     # 前端
├── docs/                         # 文档
├── examples/                     # 测试用例
├── tests/                        # 示例代码
├── .evn.example                  # 环境变量
├── pyproject.toml                # 项目配置
├── uc.lock                       # 依赖锁文件
├── .gitignore                    # git 忽略文件
└── README.md                     # 项目描述
```