# 卖家母版选择

两份母版共享原 WPS 发票的页边距、左右买卖方栏、灰色七列表头、表格格线及页尾。母版只保留卖家静态资料；日期、订单号、买家、商品、金额由本单填入。

| 标识 | 母版文件 | 顶部公司名称 | Sales |
| --- | --- | --- | --- |
| `jiuyue` | `assets/blank-reference-template.pdf` | `shenzhenshijiuyuekejiyouxiangongsi` | `JiuYue_KeJi` |
| `renhaoyuan` | `assets/blank-renhaoyuan-template.pdf` | `shenzhenshirenhaoyuanmaoyiyouxiangongsi` | `Renhaoyuan` |

顶部写完整公司名称，不用 `Renhaoyuan` 店铺简称替代。Renhaoyuan 的已确认电话为 `+8613242020247`，邮箱为 `renhaoyuanmaoyi@outlook.com`；地址统一为：

```text
longgangqu pinghujiedao hehuashequ huanandadao yihao
huananguoji yinshua zhipin baozhuang wuliuqu erqi 2haolou 2B109
shenzhenshi, Guangdong 518111
CN
```

这是龙岗区平湖街道禾花社区华南大道一号、华南国际印刷纸品包装物流区二期2号楼2B109的拼音写法。原始中文地址和印刷拼音地址均存入 `assets/seller-templates.json` 以核对来源；发票不打印中文，不打印 Business registration / 商业注册号，也不把注册号写入 VAT number。

## 选择方法

- CLI：`--template renhaoyuan` 或 `--template jiuyue`。
- JSON：`"seller_template": "renhaoyuan"`，也接受已保存的卖家别名。
- `seller.company`、`seller.store_name` 或 `seller.sales_name` 与已保存身份一致时自动匹配；已识别的多个选择必须一致。
- 原订单复制文本中的 `Profil vendeur Amazon.fr : Renhaoyuan` 会选中对应母版。
- 不认识的母版、相互矛盾的卖家或不匹配的地址/电话/邮箱不能出单。卖家未说明时助手先确认；脚本保留原母版默认值只用于兼容旧调用。

非默认卖家缺少对应 PDF 时停止，不退回原卖家母版。新增卖家时先确认完整公司名称、地址和联系方式，创建不含买家信息的独立 PDF 并在此登记，不修改已有卖家的母版。

## 买家姓名

配送地址首行可能是取件柜或机构，并不证明它是个人姓名。若用户明确指定首行作为发票姓名，则按该订单填写 `buyer.name`，不重复放入 `address_lines`；否则使用已确认收件人。不要把某单的取件点保存为固定模板买家。
