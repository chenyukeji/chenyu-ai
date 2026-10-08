# 晨玙 Amazon 发货插件

面向发货岗位的固定模板文档生成插件。当前包含 Amazon.fr EUR 商业发票能力，可把已确认的 Amazon 订单字段填入去敏的原始 PDF 母版，并在交付前核对购买日期、金额、买家信息和版式。

## 包含能力

- `chenyu-invoice`：生成 Amazon.fr EUR 商业发票 PDF
- 校验订单编号、购买日期、买家、商品、数量、金额和固定 VAT 计算口径
- 支持法国及版式可容纳的其他 EUR 收件国家，并核对运费促销后的净运费
- 保留原 WPS PDF 母版的栏位、线条、标签和版式
- 渲染检查生成结果，不上传 Seller Central 或联系买家

## 适用边界

当前母版只适用于指定卖家主体、Amazon.fr EUR 订单和现有固定版式。法国以外的 EUR 收件国家只能替换国家值，不改变版式；其他卖家、销售站点、币种或其他类型的发货模板，需要提供并验证对应的新母版后再增加能力。

真实订单、客户姓名、地址、税号和原始未去敏发票不得提交到 GitHub 或打入插件；仓库只保留虚构示例和已清理母版。

默认输出位于 `outputs/chenyu-fahuo/commercial-invoice/<YYYY-MM-DD_订单编号>/`。详细规则见 [输出目录规范](references/output-paths.md)。

## 目录说明

```text
chenyu-fahuo/
├── .codex-plugin/
│   └── plugin.json
├── plugin.json
├── references/
│   └── output-paths.md
└── skills/
    └── chenyu-invoice/
```

打包分发时，ZIP 根层应直接包含 `plugin.json` 和 `skills/`。详细仓库约定与安装说明见项目根目录的 [README](../../README.md)。
