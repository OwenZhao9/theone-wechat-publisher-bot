---
name: wechat-draft
description: 当用户明确要求把 .push.md 放入或更新微信公众号草稿箱，或检查微信接口权限时，使用随附脚本生成预览并调用微信官方草稿接口；不执行公开发布、群发或定时群发。
---

# 公众号草稿

这个技能依赖 TheOne 的 `files` 和 `shell`，以及微信官方接口的网络访问。它不依赖 Computer Use。

## 路由

- 首次配置、凭证和 IP 白名单问题：读取 [配置说明](./references/setup.md)。
- 接口错误或能力边界：读取 [故障与权限](./references/troubleshooting.md)。

## 工作流程

1. 只有用户明确要求创建、推送或更新草稿时，才调用微信接口。普通写作和本地预览不产生外部修改。
2. 检查 `.push.md`、封面和正文图片均存在，且不包含私人信息。创建或更新草稿必须有封面。
3. 从本 `SKILL.md` 的实际绝对路径确定技能目录，把下面命令中的 `SKILL_DIR` 替换为该目录。不要假设用户工作文件夹中存在 `skills/`，也不要把文章写进技能目录。
4. 始终先运行：

   ```bash
   python3 "SKILL_DIR/scripts/wechat_publish.py" --dry-run ARTICLE.push.md
   ```

5. 预览成功后，按用户要求执行一个操作：

   ```bash
   # 创建新草稿
   python3 "SKILL_DIR/scripts/wechat_publish.py" ARTICLE.push.md

   # 更新已有草稿；media_id 必须来自该公众号真实草稿
   python3 "SKILL_DIR/scripts/wechat_publish.py" --update MEDIA_ID ARTICLE.push.md
   ```

6. 如需只读检查权限，运行：

   ```bash
   python3 "SKILL_DIR/scripts/wechat_publish.py" --check-permissions
   ```

7. 根据脚本真实输出报告结果。只有出现 `media_id` 或更新成功响应时才能声称草稿已创建或更新。

## 禁止事项

- 不调用 `freepublish/submit`、`message/mass/sendall` 或其他公开发布、群发接口。
- 不设置定时群发，不模拟点击公众号后台，不声称文章已经发表。
- 不在命令、日志、文章、Bot 包或回复中回显 AppSecret、访问令牌等凭证。
- 缺少网络、凭证、白名单、接口权限、封面或真实素材时，说明具体缺口并停止相关步骤，不制作假结果。
