# 公众号文章文件格式

保存为 UTF-8 编码的 `.push.md` 文件：

```markdown
---
title: 文章标题
author: 作者名
digest: 不超过 120 字的摘要
cover: ./images/cover.png
open_comment: 1
fans_only_comment: 0
---

正文从这里开始，不要重复写一级标题。

## 小标题

正文内容。

![图片说明](./images/step-1.png)
```

## 字段

- `title`：必填，最多 64 字。
- `author`：选填。
- `digest`：建议填写，最多 120 字。
- `cover`：创建草稿时必填；支持相对文章文件的路径、绝对路径或 `~` 路径。
- `source_url`：仅在用户明确要求“阅读原文”时添加。
- `open_comment`：`1` 开启评论，`0` 关闭。
- `fans_only_comment`：`1` 表示仅粉丝可评论。
- `theme`：选填；当前支持默认主题和 `book`。

## 正文支持

- 二级、三级标题
- 段落、引用、列表、分割线
- 加粗、斜体、行内代码、代码块
- 本地或远程图片
- Markdown 链接；非公众号链接会转为文末脚注

不要把凭证、访问令牌、验证码或私人信息写入文件。创建草稿前先运行 `--dry-run` 检查预览。
