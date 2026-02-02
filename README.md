# Fund-AI-Advisor 🚀

基于技术分析（RSI/MACD/MA）与 AI 情绪分析（Gemini）的智能基金投顾系统。

## 特点
- **双模分析**: 技术指标 + 大模型新闻情绪分析
- **智能定投**: 超卖时自动加仓，超买时提示止盈
- **零成本部署**: 完全基于 GitHub Actions + 免费 API

## 快速开始
1. Fork 本仓库（设为 Private）
2. 配置 Secrets: `GEMINI_API_KEY` 和 `PUSHPLUS_TOKEN`
3. 修改 `config.yaml` 中的基金代码
4. 在 Actions 页面手动运行测试

## 文件说明
- `config.yaml`: 基金列表与策略参数
- `main.py`: 主程序入口
- `.github/workflows/`: 每日定时运行配置

## 风险提示
本系统仅供参考，不构成投资建议。市场有风险，投资需谨慎。