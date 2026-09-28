# 晨玙 Amazon 采购插件

面向采购和供应链岗位的分析插件，用于比较供应商条件、制定采购或补货计划，并整理交期、质量、物流和库存风险。

## 包含能力

- 供应商报价和条件标准化
- 1688 候选供应商低频采集、人工验证码交接和断点续跑
- MOQ、交期、质量、付款及物流比较
- 销售预测和库存驱动的采购建议
- 交期跟踪、异常整理和供应风险预警

## 常见输入

- 产品需求和目标规格
- 供应商报价单及沟通记录
- MOQ、交期、付款、物流和质检资料
- 销售预测、库存、在途和安全库存数据

## 交付与边界

插件输出可审核的比较、采购计划和风险建议。它不会代替员工联系供应商、承诺订单、签约、下单或付款；缺失和冲突信息会作为待确认项保留。

1688 采集使用单个可见 Playwright 持久浏览器，默认每个关键词读取首屏前 20 条、只进入前 5 个详情页。验证码和登录由员工在浏览器中完成；插件只负责暂停、保存检查点、检测验证结束并续跑，不破解或绕过网站安全验证。运行参数与状态协议见 [1688 供应商采集](skills/chenyu-caigou/references/1688-collector.md)。

默认输出位于 `outputs/chenyu-caigou/`，先按 `supplier-comparison`、`procurement-plan`、`supply-tracking` 等交付部分分大目录，再使用 `YYYY-MM-DD_产品简称` 建立本次任务目录。详细规则见 [输出目录规范](references/output-paths.md)。

## 目录说明

```text
chenyu-caigou/
├── .codex-plugin/
│   └── plugin.json
├── plugin.json
├── references/
│   └── output-paths.md
├── requirements-browser.txt
└── skills/
    └── chenyu-caigou/
        ├── references/
        │   └── 1688-collector.md
        └── scripts/
            ├── collector_1688.py
            └── run.py
```

打包分发时，ZIP 根层应直接包含 `plugin.json` 和 `skills/`。详细的仓库约定与安装说明见项目根目录的 [README](../../README.md)。
