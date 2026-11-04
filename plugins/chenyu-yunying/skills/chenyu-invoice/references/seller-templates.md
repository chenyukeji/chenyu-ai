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

## 浏览器采集卖家地址后的拼音格式

从用户提供的 Amazon 卖家资料页读取公开的公司名称、地址、电话、邮箱和 VAT 字段；通用网页读取失败不能直接判定页面不可访问，可使用已配置的 Chromium 浏览器读取。出现登录、验证码或访问限制时停止，不绕过。卖家资料页域名不替代订单销售渠道，也不决定该订单税率。

浏览器采集到的中文卖家地址，填写发票时统一按用户确认的紧凑拼音格式处理：

- 街道、社区、村名及门牌地址使用不带声调的小写拼音连写，不按音节或词语插入空格。例如 `平湖街道上木古村116号305` → `pinghujiedaoshangmugucun116hao305`。
- 门牌号、楼栋号、房间号、邮编和原有字母编号保留，不能漏掉 `116`、`305`、`2B109` 等地址细节；不将街道、区、村改写成英语意译。
- 第一行填写街道及详细门牌；第二行按 `城市拼音, 区拼音, 省名拼音 邮编` 排列，例如 `shenzhenshi, longgangqu, Guangdong 518111`；第三行填写来源中的国家代码并全大写，如 `CN`。**大小写属于固定格式**：街道、村名、城市和区的拼音全部小写连写；省名拼音仅首字母大写，如 `Guangdong`；房间/楼栋等原有字母编号保留来源大小写，如 `2B109`，不对整段地址统一转大写或每词首字母大写；缺失成分不编造，长详细地址可按母版栏宽增加分行，不截断。
- 原始中文地址及资料页 URL 保留作为核对依据；发票打印拼音地址。对已保存卖家，中文地址与原资料一致时复用该母版已确认的拼音写法；地址变化时先核对并更新对应母版，不能只修改 JSON 后继续打印旧地址。

JiuYue 的已确认印刷地址为以下三行（`ADD:` 是模板标签，不属于地址正文）：

```text
pinghujiedaoshangmugucun116hao305
shenzhenshi, longgangqu, Guangdong 518111
CN
```

## 选择方法

- CLI：`--template renhaoyuan` 或 `--template jiuyue`。
- JSON：`"seller_template": "renhaoyuan"`，也接受已保存的卖家别名。
- `seller.company`、`seller.store_name` 或 `seller.sales_name` 与已保存身份一致时自动匹配；已识别的多个选择必须一致。
- 原订单复制文本中的 `Profil vendeur Amazon.fr : Renhaoyuan` 会选中对应母版。
- 不认识的母版、相互矛盾的卖家或不匹配的地址/电话/邮箱不能出单。卖家未说明时助手先确认；脚本保留原母版默认值只用于兼容旧调用。

固定卖家缺少对应 PDF 时停止，不退回其他卖家母版。自有卖家可以使用 `seller_template: imported` 与 `seller_confirmed: true`，由已保存并核对的快照提供完整公司名和地址，联系方式有据才填。生成脚本支持此分支：只沿用原空白 PDF 的图形，删除全部预印卖家值并填写快照，不修改插件里的固定母版、不把私人卖家快照登记到公开仓库。确认来自实际用户或已批准保存资料，不重复索取已有资料，也不伪造确认。

PLN 另需本单明确同意按原币开票并调整母版，使用 `template_currency: PLN`；这不授权换汇。其他币种尚未实现。

## 买家姓名

先核对买家开票留言是否明确指向本订单，有则优先用其公司/个人抬头、地址与税号，写入 `billing_request`；不要因配送资料不完整而拒绝已有完整账单资料。没有留言才用配送地址第一行原文，个人、公司、机构或取件点均可，不改用联系买家显示名。抬头不重复放入 `address_lines`，不把某单买家保存为固定模板。
