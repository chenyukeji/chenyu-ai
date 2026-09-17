# chenyu-ai

晨玙科技 Amazon AI 工作插件仓库。仓库按公司岗位维护四个相互独立、可单独分发的插件：美工、运营、开发和采购。

## 当前插件

| 插件 | 面向岗位 | 当前 Skills |
| --- | --- | --- |
| `chenyu-amazon-creative` | Amazon 美工 | `chenyu-zuotu`、`chenyu-jingxiu` |
| `chenyu-amazon-operation` | Amazon 运营 | `chenyu-yunying` |
| `chenyu-amazon-development` | Amazon 产品开发 | `chenyu-kaifa` |
| `chenyu-amazon-procurement` | Amazon 采购 | `chenyu-caigou` |

## 统一目录规范

```text
plugins/
├── chenyu-amazon-creative/
│   ├── plugin.json
│   └── skills/
│       ├── chenyu-zuotu/
│       │   ├── SKILL.md
│       │   ├── agents/
│       │   ├── assets/
│       │   ├── references/
│       │   └── scripts/
│       └── chenyu-jingxiu/
│           ├── SKILL.md
│           ├── agents/
│           └── assets/
├── chenyu-amazon-operation/
│   ├── plugin.json
│   └── skills/chenyu-yunying/
├── chenyu-amazon-development/
│   ├── plugin.json
│   └── skills/chenyu-kaifa/
└── chenyu-amazon-procurement/
    ├── plugin.json
    └── skills/chenyu-caigou/
```

每个插件遵循以下规则：

- 根目录使用 `plugin.json` 描述插件，`skills/` 保存该岗位的实际能力。
- 每个 Skill 都有 `SKILL.md`；`agents/openai.yaml` 只描述该 Skill 在界面中的名称和默认提示。
- `assets/`、`references/`、`scripts/` 仅在有真实内容时建立，不保留空目录。
- 后续需要 MCP、App 或独立 Agent 时，只在对应插件中增加，四个插件仍可分别安装和升级。

## 员工安装

管理员或维护者分别打包 `plugins/` 下的四个目录，ZIP 根层必须直接看到 `plugin.json` 和 `skills/`。员工在 ChatGPT 工作区的插件管理页面上传自己岗位对应的 ZIP，安装后新建对话即可使用。

四个部门使用各自的压缩包，互不依赖；更新某个部门时只需重新发放该部门 ZIP。

## 仓库中的其他目录

仓库中现有的业务原型、Schema、示例和文档继续作为内部研发参考。它们不属于员工插件的安装内容，也不会被装入岗位 ZIP。

## 边界

- 示例文件不能当作实时调研数据。
- 未经明确授权，不修改 Amazon 店铺、广告或 Listing，不联系供应商，不下单或付款。
- Amazon New Releases 的定时采集、浏览器导航、快照入库和数据库维护属于同级项目 `../amazon-new-release-collector`。
