# clinic-agent

clinic-agent 是一个安全优先的医疗预问诊与分诊助手。它通过规则引擎先识别急症警示，再为常见症状推荐就医级别和科室；可选接入 OpenAI 兼容模型来改善回复语气和信息整理能力，但模型始终不会绕过规则分诊与安全回退。

> 本项目不是医疗器械，不提供诊断、处方或急救服务。遇到急症请立即拨打 120 或前往急诊。

## 已完成的核心能力

- 中文网页版预问诊界面，支持会话恢复、历史记录、安全级别和科室建议展示。
- 四级安全分诊：急症、24小时内就医、择期门诊、居家观察；信息不足时先追问。
- 覆盖心肺、神经、消化、妇产、儿科、皮肤、耳鼻喉、眼、口腔、心理等常见科室路由。
- 简单否定识别，例如“没有胸痛”不会被直接判为急症。
- SQLite 会话与消息持久化，可生成便于就诊沟通的文本摘要。
- 可选 OpenAI 兼容模型后端；无模型密钥时仍可用规则模式完整运行。
- 模型请求失败或回复缺少急症升级提示时自动回退到规则回复。
- 零第三方运行时依赖，Python 标准库即可启动和测试。
- 16 个自动化测试覆盖分诊、存储、服务层、HTTP API 与静态页面。

## 快速开始

要求 Python 3.10+。

```bash
python3 -m clinic_agent
```

打开 <http://127.0.0.1:8000> 即可使用。默认使用本地 SQLite 文件 `clinic_agent.db`，并只监听 `127.0.0.1`。

### 运行测试

```bash
python3 -m unittest discover -s tests -v
```

## 配置模型后端（可选）

项目默认使用规则分诊。如需接入 OpenAI 或兼容网关：

```bash
export OPENAI_API_KEY="你的密钥"
export OPENAI_BASE_URL="https://api.openai.com/v1"
export CLINIC_AGENT_MODEL="gpt-4o-mini"
python3 -m clinic_agent
```

可用环境变量：

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `HOST` | `127.0.0.1` | 监听地址。对外部署前请先完成鉴权与传输加密。 |
| `PORT` | `8000` | 监听端口。 |
| `CLINIC_AGENT_DB` | `clinic_agent.db` | SQLite 数据文件路径。 |
| `OPENAI_API_KEY` | 空 | 设置后启用模型后端。 |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI 兼容地址。 |
| `CLINIC_AGENT_MODEL` | `gpt-4o-mini` | 模型名。 |
| `CLINIC_AGENT_TIMEOUT` | `30` | 模型请求秒数。 |
| `CLINIC_AGENT_MAX_MESSAGE_CHARS` | `4000` | 单条消息最大长度。 |

## API 概览

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/health` | 服务与健康状态。 |
| `POST` | `/api/sessions` | 创建问诊会话。 |
| `GET` | `/api/sessions` | 获取历史会话。 |
| `GET` | `/api/sessions/{id}` | 获取会话及全部消息。 |
| `POST` | `/api/sessions/{id}/messages` | 发送症状消息并获取分诊回复。 |

详见 [`docs/API.md`](docs/API.md)。

## 项目结构

```text
clinic_agent/
  config.py       环境配置
  triage.py       规则分诊与安全提示
  llm.py          可选模型适配与安全回退
  storage.py      SQLite 持久化
  service.py      业务服务层
  server.py       HTTP API 与静态页面服务
  static/         网页界面
tests/            自动化测试
docs/             产品、安全与接口说明
```

## 部署提醒

- 当前版本适合本机试用、内网演示或作为原型部署。
- 若要面向公网，必须增加登录/授权、HTTPS、访问日志留存策略、数据删除机制、限流和安全管理。
- 不要让用户上传身份证号、住址、检查影像等高敏数据，除非已另行完成合规评估与加密存储。
- 医疗相关产品上线前应由有资质的医务人员与法务/合规人员审核规则和文案。

## 路线建议

1. 邀请医务人员审核并扩充急症规则、科室映射与否定表达。
2. 增加账号体系、角色权限、会话删除和审计日志。
3. 增加结构化生命体征输入与症状时间线。
4. 加入真实场景评测集，跟踪急症漏报率为 0 的目标。
5. 若接入模型，记录脱敏样本并定期评估安全性和一致性。

## 许可

MIT License. See [LICENSE](LICENSE).
