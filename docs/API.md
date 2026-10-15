# API 说明

所有响应均为 UTF-8 JSON。除静态资源外，接口均不缓存。

## 服务状态

### `GET /api/health`

```json
{
  "status": "ok",
  "service": "clinic-agent",
  "model_backend": "rule_based",
  "disclaimer": "本系统提供就医分诊参考，不提供医疗诊断或处方。"
}
```

`model_backend` 为 `rule_based` 表示规则模式，`configured` 表示已配置模型后端。

## 创建会话

### `POST /api/sessions`

请求：

```json
{
  "patient_alias": "小李",
  "age_years": 30,
  "sex": "female"
}
```

- `patient_alias`：可选，最长 80 字符，建议使用昵称。
- `age_years`：可选，0-120 的整数。
- `sex`：可选，`female`、`male`、`other` 或 `unknown`。

响应状态码为 `201`，`session` 中包含唯一 `id`。

## 查询会话

### `GET /api/sessions?limit=50`

返回按更新时间倒序的会话，`limit` 范围为 1-100。

### `GET /api/sessions/{id}`

返回 `session` 与 `messages`。每条消息包含：

- `role`：`user` 或 `assistant`
- `content`：文本内容
- `triage`：助手消息关联的分诊结果，用户消息为 `null`
- `created_at`：UTC ISO-8601 时间

## 发送症状消息

### `POST /api/sessions/{id}/messages`

请求：

```json
{
  "content": "咳嗽两天，喉咙痛，没有胸痛"
}
```

响应：

```json
{
  "session": {},
  "user_message": {},
  "assistant_message": {},
  "triage": {
    "urgency": "routine",
    "urgency_label": "建议择期门诊评估",
    "departments": ["呼吸内科"],
    "reasons": [],
    "follow_ups": [],
    "care_advice": [],
    "red_flags": []
  }
}
```

`urgency` 取值：

- `emergency`：疑似急症，立即拨打120或去急诊
- `urgent`：建议24小时内就医
- `routine`：建议择期门诊评估
- `self_care`：可先居家观察
- `info_needed`：需要补充信息

## 错误格式

```json
{ "error": "content cannot be empty" }
```

常见状态码：`400` 请求无效、`404` 会话或页面不存在、`413` 请求体过大、`500` 服务内部错误。
