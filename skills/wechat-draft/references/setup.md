# 微信接口配置

## 依赖

- 微信公众号 AppID 与 AppSecret。
- 目标公众号具有草稿接口权限。
- 调用网络的出口 IP 已加入 API IP 白名单。
- Python 3、`curl`；图片超过限制时还需要 macOS 自带的 `sips`。

## 凭证位置

优先级从高到低：

1. 命令参数 `--config /path/to/wechat.json`
2. 环境变量 `WECHAT_APPID`、`WECHAT_APPSECRET`
3. `~/.config/theone-wechat-publisher/wechat.json`
4. 兼容旧配置 `~/.ai-daily/wechat.json`

文件内容：

```json
{"appid":"wx...","secret":"..."}
```

配置文件必须在 Bot 包之外，并设置为仅当前用户可读：

```bash
chmod 600 ~/.config/theone-wechat-publisher/wechat.json
```

不要在对话里回显凭证，不要把配置文件加入 Git 仓库。

## API IP 白名单

1. 打开微信开发者控制台，在「我的业务与服务」中选择「公众号」。
2. 进入目标公众号的「基础信息」。
3. 在「开发密钥」区域编辑「API IP 白名单」。
4. 添加脚本 `40164` 报错中 `invalid ip` 后面的地址。

公网 IP 是微信服务器看到的网络出口地址。切换 Wi-Fi、手机热点、VPN、代理、电脑或服务器时都可能改变；`192.168.x.x`、`10.x.x.x` 等内部地址不要加入白名单。
