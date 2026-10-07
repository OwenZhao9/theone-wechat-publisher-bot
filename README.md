# 公众号文章助手

这是一个可直接导入 TheOne 的 Skill 型 Bot。它复用 TheOne 已配置的 AI 模型，不包含聊天后台、网页应用或新的模型服务。

## 能做什么

- 把用户提供的主题、文字、录屏截图和本地资料整理为公众号文章。
- 生成符合约定格式的 `.push.md` 文件和手机宽度 HTML 预览。
- 上传本地封面与正文图片，通过微信官方接口创建公众号草稿。
- 使用已有草稿的 `media_id` 更新文章，避免重复创建草稿。
- 只读查询草稿、公开发布和群发接口是否有权限。
- 使用 TheOne 内置 Browser Use 打开公众号后台，协助发表草稿或设置定时。

## 明确边界

- 微信接口脚本只创建或更新草稿，不调用公开发布或群发接口；网页发表和定时由单独的浏览器 Skill 完成。
- 公众号后台是网页，因此需要 TheOne 内置 Browser Use，不需要 Computer Use。Browser Use 会操作 TheOne 应用内浏览器，并沿用其中已有的公众号登录状态。
- Jev 是用于比较和风险判断的模型，不是浏览器控制工具；实际打开、点击网页的是 TheOne 内置的 `aionui-browser`。
- 登录、扫码和验证码由用户本人完成。最终发表或确认定时前，Bot 必须再次显示文章标题、动作和时间并取得确认。
- 当前 Bot 没有图片生成工具。它可以使用用户提供且已确认可用的本地图片；缺少封面时会明确提示，不会伪造生成结果。
- Bot 不包含任何 AppID、AppSecret、访问令牌、账号或私人数据。

## 导入

在 TheOne 中打开 **Bot 广场 → 导入 Bot**，选择这个包含 `bot.json` 的文件夹。不要只选择 `skills` 子目录。

## 首次配置

微信接口需要 AppID、AppSecret 和 API IP 白名单。把凭证保存在 Bot 文件夹之外：

```bash
mkdir -p ~/.config/theone-wechat-publisher
chmod 700 ~/.config/theone-wechat-publisher
printf '%s\n' '{"appid":"wx...","secret":"..."}' > ~/.config/theone-wechat-publisher/wechat.json
chmod 600 ~/.config/theone-wechat-publisher/wechat.json
```

也可以设置环境变量 `WECHAT_APPID` 和 `WECHAT_APPSECRET`。已有 `~/.ai-daily/wechat.json` 时，脚本会兼容读取，但不会复制它。

在微信开发者控制台中设置 IP 白名单：

1. 展开「我的业务与服务」。
2. 选择「公众号」，进入目标账号。
3. 在「基础信息」页找到「开发密钥」。
4. 编辑「API IP 白名单」。
5. 如果脚本报 `40164`，添加报错中 `invalid ip` 后面的地址。

## 文件格式与使用

文章格式见 `skills/wechat-article/references/article-format.md`。

```bash
# 只生成预览，不调用微信接口
python3 skills/wechat-draft/scripts/wechat_publish.py --dry-run path/to/article.push.md

# 创建草稿
python3 skills/wechat-draft/scripts/wechat_publish.py path/to/article.push.md

# 覆盖更新已有草稿的第一篇文章
python3 skills/wechat-draft/scripts/wechat_publish.py --update MEDIA_ID path/to/article.push.md

# 只读检查接口权限
python3 skills/wechat-draft/scripts/wechat_publish.py --check-permissions
```

脚本只依赖 Python 3 标准库、`curl` 和 macOS 自带的 `sips`。调用微信接口时需要网络连接。网页发表或定时还需要 TheOne 内置 Browser Use 可用，并且用户已在应用内浏览器登录公众号后台。

## 已验证范围

- 2026-10-02：复用的推送引擎已在目标公众号真实创建并多次更新含封面与正文图片的草稿。
- 2026-10-04：本 Bot 的可移植脚本已通过本地预览和结构检查；当天的微信权限复查被 `40164` 拦截，因为当前网络出口 IP 尚未加入白名单。
- 最近一次成功查询中，实测账号具有 `draft/add` 草稿权限；`freepublish/submit` 和 `message/mass/*` 返回无权限，因此脚本没有包装这两个接口。网页后台是否能发表或定时，需由 Browser Use 读取真实页面后判断。重新加入当前 IP 后，可用 `--check-permissions` 再次确认接口权限。

## 数据与安全

- 外部公开内容不等于允许复制。只使用用户拥有、获得授权或符合引用条件的文字和图片。
- 截图中的邮箱、验证码、生日、账号标识和私人消息不得直接发布。
- 脚本缓存的访问令牌保存在 `~/.cache/theone-wechat-publisher/`，不在 Bot 包内。

## 许可证

本 Bot 包内原创说明和脚本按 Apache-2.0 许可证提供，详见 `LICENSE`。
