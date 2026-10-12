<p align="center"><img src="docs/assets/hero.svg" alt="Strata Sprint" width="100%"></p>

<p align="center"><a href="README.md">English</a> · <b>简体中文</b> · <a href="https://longweihan.github.io/strata-sprint/">交互式性能报告</a> · <a href="docs/INSTALL.md">安装</a></p>

# 让长会话更快接着跑

在同一张 **RTX PRO 6000 Blackwell** 上，切回 32K 主会话的首字等待从 **7.625 秒降到 0.199 秒**，12 次测量平均约快 **38.3 倍**，对照为我们完整记录的 Strata 0.1.43 配置。

**Strata Sprint 是基于 [Strata](https://github.com/Niko1221/Strata) 的 PRO 6000 优化发行版。** Strata 提供计算内核、API 和会话状态缓存；本项目提供经过实测的硬件配置、独立进程监督、配置检查和公开实验记录。两组对照使用相同的上游提交。

收益集中在长会话恢复，逐字生成速度基本不变。首次保存大上下文需要复制状态，部分短请求会变慢。完整结果保留这些代价。

<img src="docs/assets/benchmark.svg" alt="完整配置对照图" width="100%">

## 实测对比

环境：Linux、20 vCPU、160 GiB 内存、97,887 MiB 可见显存；SC117 Qwen3.8-Flash-Next-GSQ-RCO-abliterated IQ3_S，FP16 KV，131072 上下文，MTP 4。

| 完整配置下的项目 | Strata 基线 | Sprint |
| :--- | ---: | ---: |
| 切回 32K 主会话首字 | 7.625 秒 | **0.199 秒** |
| 混合会话序列中的 32K 新输入 | 7.310 秒 | **6.544 秒** |
| 混合序列中的 123K 新输入 | 25.770 秒 | **25.095 秒** |
| 大上下文之后的 4K 新输入 | **1.526 秒** | 2.865 秒 |
| 代码生成 | 234.4 token/s | 234.6 token/s |
| 推理生成 | 223.8 token/s | 223.3 token/s |
| 说明文字生成 | 164.0 token/s | 163.6 token/s |
| 观测显存峰值 | **56.79 GiB** | 60.14 GiB |

首字延迟在 GPU 服务器本机的 HTTP 客户端计时，包含引擎保存/恢复状态的开销，不含远程客户端网络耗时。比较对象是[公开记录的基线参数](profiles/baseline.example.json)，不能推广为优于所有 Strata 配置或未来版本。

另有独立缓冲区单项实验：4K、32K、123K 新输入首字等待分别缩短 31.0%、12.0%、4.9%。这与上面的完整配置实验分开统计。[449 条记录与方法](docs/BENCHMARKS.md)。

## 做了什么

- 使用独立的 8192-token 提示词缓冲区，让 GPU 上的专家权重保持驻留。
- 4 个会话共享 16 GiB 主机内存缓存，切回时恢复已有状态。
- 缓存准入保留至少 16 GiB 可用内存，并使用明确的主机/容器内存上限；小于 2048 tokens 的请求不占缓存槽。
- 保持原模型、FP16 KV、MTP 4、采样和思考配置；排除改变 logits 或没有稳定收益的激进开关。

这些引擎能力由上游 Strata 实现，本项目贡献是面向特定硬件的组合、验证、运行工具和可审查的数据。

## 开始使用

在 Linux GPU 服务器上执行，先准备经过验证的模型和可运行的 Strata 0.1.43 配置：

```bash
git clone --recurse-submodules https://github.com/LongWeihan/strata-sprint.git
cd strata-sprint
python3 -m pip install -e '.[bench]'
strata-sprint configure --base /srv/strata/base.json \
  --output /srv/strata/sprint.json --ram-gib 160 --port 8080
strata-sprint doctor --config /srv/strata/sprint.json \
  --engine /srv/strata/source --python /srv/strata/python/bin/python
strata-sprint serve --config /srv/strata/sprint.json \
  --engine /srv/strata/source --python /srv/strata/python/bin/python \
  --state-dir /srv/strata/sprint-state
```

`--engine` 是配置实际使用、固定到指定提交的 Strata 源码目录；仓库中的 `engine/` 是相同版本的子模块。`--python` 使用装好上游依赖的 Python。要求 PRO 6000 Blackwell 96 GB、至少 160 GiB 主机内存。模型权重单独准备，不随仓库分发。

不依赖 Molab、Claude、CC Switch 或桌面桥接。直接提供上游的 OpenAI / Anthropic API。默认仅监听本机，开放网络访问前须配置 API key。[从零安装说明](docs/INSTALL.md)。

## 精度与稳定性证据

70/70 输出正文哈希与基线一致，49/49 非会话切换的首步 logits 逐字节一致。12 次缓存续算与冷重算存在浮点路径差异，本文不把它们称为逐位一致；它们的正文在本次实验中相同。以不断线会话为参考的独立对照，验证了缓存恢复后的首步 logits 和正文一致。

三个原数学样例在两组配置中都被 512-token 上限截断，失败记录保留；增加输出空间后的补测完成并给出正确结果。有限测试不是通用精度证明。

独立监督程序只管理自己启动的进程，确认退出后退避重启，保留运行中或状态不明的引擎，不自动重放请求。新监督程序经过本地模拟与 Linux CI 验证；历史 GPU 数据测量的是相同引擎参数，尚不构成新包装的多日生产验收。[运行说明](docs/OPERATIONS.md)。

## 开源与致谢

本项目新增代码使用 MIT 许可。感谢 **Niko1221 和 Strata 贡献者**，其原始许可和源码历史保留于固定子模块中。Qwen、模型发布者以及 llama.cpp / ggml 等组件分别保留自身权利与许可。[来源说明](NOTICE.md) · [贡献指南](CONTRIBUTING.md)。
