# 开发总入口执行流程

## 路由

1. 读取运行规则并建立 Task Brief。
2. 找产品、统一候选池、需求和竞品验证：交给 `chenyu-jihui`。
3. 真实报价、现货对应、单品/多件装/组合、利润和评审：交给 `chenyu-kaifa-pingshen`。
4. 汇总开发 Excel、Product Master、部门待办和试销卡。
5. 有真实试销数据时再进入复盘。

## 第一版最短闭环

```text
Task Brief
→ 多来源 Candidate
→ 去重 Candidate Pool
→ Evidence
→ Opportunity Card
→ Supply Match
→ Economics
→ Decision
→ Development Workbook + Trial Card
```

采集器失败时允许使用结构化文件导入继续。采集失败不得被伪装成市场没有需求。

## 输入缺失处理

- 不影响当前阶段：继续执行并列入待办。
- 影响某个数字：该数字保持 pending，不猜值。
- 影响硬门槛：门槛为 unknown，不能自动通过或淘汰。
- 真实报价缺失：允许继续研究，但不能输出“成本已通过”。
- 真实平台费率缺失：利润模型只能输出部分结果或情景，不冒充最终利润。

## 写操作边界

这些 Skill 只做研究、计算和文件交付。未经明确授权，不联系供应商、不采购、不付款、不修改 Amazon 店铺、不发布 Listing、不启动广告。
