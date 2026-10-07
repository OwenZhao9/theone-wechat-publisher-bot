#!/usr/bin/env python3
"""公众号草稿发布工具。

把一个或多个 ``.push.md`` 文件转换为公众号 HTML，并通过微信官方接口创建或
更新草稿。它只使用 Python 标准库、curl，以及处理图片时的 macOS ``sips``。
脚本不会调用群发、发布或定时发表接口。

``.push.md`` 格式：
    ---
    title: 最终选定的标题
    author: 作者名
    digest: 摘要，≤120 字（留空会被自动截前 54 字，很难看）
    cover: covers/2026-08-16.jpg     # 相对本文件 / 绝对路径 / ~ 都行
    source_url: https://原文链接      # 可选；读者点「阅读原文」跳这里
    ---

    正文 markdown
"""

import argparse
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import zlib
from datetime import datetime

API = "https://api.weixin.qq.com/cgi-bin"
HOME = os.path.expanduser("~")
DEFAULT_CONFIG = os.path.join(HOME, ".config", "theone-wechat-publisher", "wechat.json")
LEGACY_CONFIG = os.path.join(HOME, ".ai-daily", "wechat.json")
STATE_DIR = os.path.join(HOME, ".cache", "theone-wechat-publisher")
TOKEN_CACHE = os.path.join(STATE_DIR, "token.json")
TMPDIR = os.path.join(STATE_DIR, "tmp")
CONFIG_PATH = None
TIMEOUT = 60

# 正文图微信只收 jpg/png 且必须 <1MB；封面走永久素材，限制松得多
IMG_MAX_BYTES = 1000 * 1000
COVER_MAX_BYTES = 4 * 1000 * 1000

# 公众号编辑器会清理 class，因此排版使用行内 style。
# 公众号编辑器会剥掉 <style> 标签和 class，只认 style="..."，没有第二条路。
STYLE = {
    "p":      "font-size:15px;line-height:1.75;letter-spacing:.5px;color:#2c3e50;margin:0 0 1.3em;",
    "h2":     "font-size:18px;line-height:1.6;font-weight:700;color:#1a1a1a;"
              "margin:2.2em 0 1em;padding-left:10px;border-left:4px solid #07c160;",
    "h3":     "font-size:16px;line-height:1.6;font-weight:700;color:#1a1a1a;margin:1.8em 0 .8em;",
    "quote":  "margin:0 0 1.3em;padding:12px 14px;background:#f7f7f7;border-left:3px solid #dbdbdb;",
    "quote_p": "font-size:14px;line-height:1.7;color:#666;margin:0 0 .6em;",
    "li":     "font-size:15px;line-height:1.75;color:#2c3e50;margin:0 0 .5em;",
    "list":   "margin:0 0 1.3em;padding-left:1.2em;",
    "code":   "font-size:13px;font-family:Menlo,Consolas,monospace;background:#f2f2f2;"
              "color:#c7254e;padding:1px 4px;border-radius:3px;",
    "pre":    "font-size:13px;line-height:1.6;font-family:Menlo,Consolas,monospace;background:#f7f7f7;"
              "color:#333;padding:14px;border-radius:4px;overflow-x:auto;margin:0 0 1.3em;",
    "hr":     "border:0;border-top:1px solid #e5e5e5;margin:2em 0;",
    "img":    "max-width:100%;display:block;margin:1.5em auto;border-radius:4px;",
    "strong": "color:#1a1a1a;font-weight:700;",
    "link":   "color:#576b95;text-decoration:none;",
    "sup":    "font-size:11px;color:#07c160;vertical-align:super;",
    "ref_h":  "font-size:14px;font-weight:700;color:#999;margin:2.5em 0 .8em;",
    "ref":    "font-size:12px;line-height:1.7;color:#999;margin:0 0 .4em;word-break:break-all;",
    # ==高亮== 的底色。默认跟加粗一样，只有换了配色的才真的上荧光笔。
    "mark":   "color:#1a1a1a;font-weight:700;",
}

DEFAULT_STYLE = dict(STYLE)

# front matter 里写 theme: <名字> 可换配色。不写则使用默认微信绿。
# 只覆盖要改的键，其余从 DEFAULT_STYLE 继承。
THEMES = {
    # 《深入浅出 DeepSeek Harness》的宜家蓝黄。黄在浅底上做不了字，只当荧光笔。
    "book": {
        "p":      "font-size:15px;line-height:1.78;letter-spacing:.5px;color:#3A3F45;margin:0 0 1.35em;",
        "h2":     "font-size:18px;line-height:1.6;font-weight:600;color:#0E1116;"
                  "margin:2.4em 0 1em;padding-left:11px;border-left:4px solid #0058A3;",
        "h3":     "font-size:16px;line-height:1.6;font-weight:600;color:#0E1116;margin:1.9em 0 .8em;",
        "quote":  "margin:0 0 1.5em;padding:15px 18px;background:#EAF1F8;"
                  "border:1px solid #C3D8EA;border-radius:11px;",
        "quote_p": "font-size:14.5px;line-height:1.75;color:#3A3F45;margin:0 0 .6em;",
        "li":     "font-size:15px;line-height:1.78;color:#3A3F45;margin:0 0 .5em;",
        "code":   "font-size:13px;font-family:Menlo,Consolas,monospace;background:#F1F3F5;"
                  "color:#0E1116;padding:2px 6px;border-radius:4px;",
        "pre":    "font-size:12.5px;line-height:1.8;font-family:Menlo,Consolas,monospace;"
                  "background:#F1F3F5;color:#0E1116;padding:15px 18px;border-radius:9px;"
                  "overflow-x:auto;margin:0 0 1.5em;",
        "hr":     "border:0;border-top:1px solid #E4E6E9;margin:2.4em 0;",
        "strong": "color:#0E1116;font-weight:600;",
        "mark":   "color:#0E1116;font-weight:600;padding:0 2px;"
                  "background:linear-gradient(transparent 56%,#FFF3B8 56%,#FFF3B8 94%,transparent 94%);",
        "link":   "color:#00457F;text-decoration:none;",
        "sup":    "font-size:11px;color:#0058A3;vertical-align:super;",
    },
}


def apply_theme(meta):
    """按 front matter 的 theme 换配色。返回上一套，用完要还回去（多图文时互不串色）。"""
    prev = dict(STYLE)
    STYLE.clear()
    STYLE.update(DEFAULT_STYLE)
    name = (meta.get("theme") or "").strip().lower()
    if name and name not in THEMES:
        warn(f"没有叫 {name} 的配色，用默认那套。现有：{'、'.join(THEMES)}")
    STYLE.update(THEMES.get(name, {}))
    return prev

ERR_HINTS = {
    40001: "AppSecret 不对。请在微信开发者控制台重置后，更新电脑上的 wechat.json。",
    40007: "media_id 无效——封面素材可能已被删除，换一张。",
    40164: "调用方 IP 不在白名单。去微信开发者控制台「我的业务与服务 → 公众号 → "
           "基础信息 → 开发密钥 → API IP 白名单 → 编辑」添加微信报错中显示的 IP。",
    41005: "没收到媒体文件——检查图片路径是否存在。",
    45009: "接口调用超频，等一会儿再试（stable_token 已做缓存，正常不该撞到）。",
    48001: "当前公众号没有调用这个接口的权限。请运行 --check-permissions，并在后台接口权限页核对。",
    76022: "当前公众号没有调用这个接口的权限。请运行 --check-permissions 查看草稿、发布和群发权限。",
    53404: "账号已被限制，去后台看通知。",
}


# ---------------------------------------------------------------- 基础设施

def die(msg):
    print(f"\n✗ {msg}\n", file=sys.stderr)
    sys.exit(1)


def warn(msg):
    print(f"  [warn] {msg}", file=sys.stderr)


def run(cmd, timeout=TIMEOUT):
    """跑 curl/sips。返回 (ok, stdout)。"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            return False, (r.stderr or "").strip()
        return True, r.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return False, str(e)


def my_ip():
    ok, out = run(["curl", "-sS", "-m", "10", "https://ifconfig.me"], timeout=15)
    return out.strip() if ok and out.strip() else "（取不到，自己搜「我的IP」）"


def check(data, what):
    """微信所有接口都用 errcode 报错，0 或缺省即成功。"""
    if not isinstance(data, dict):
        die(f"{what}：返回的不是 JSON —— {str(data)[:200]}")
    code = data.get("errcode", 0)
    if code == 0:
        return data
    hint = ERR_HINTS.get(code, "")
    if code == 40164:
        # 微信在 errmsg 里回了它实际看到的 IP，那才是要加白名单的那个。
        # 本机 curl 查到的 IP 可能走了不同线路（代理/VPN），照抄会白忙一场。
        seen = re.search(r"invalid ip ([0-9]{1,3}(?:\.[0-9]{1,3}){3})", str(data.get("errmsg", "")))
        if seen:
            hint += f"\n    ★ 白名单要加这个（微信实际看到的）：{seen.group(1)}"
            hint += f"\n      本机自查的是 {my_ip()}——不一致就以上面那个为准。"
        else:
            hint += f"\n    你现在的公网 IP 是：{my_ip()}"
    msg = f"{what} 失败：errcode={code} {data.get('errmsg', '')}"
    if hint:
        msg += f"\n  → {hint}"
    die(msg)


def post_json_raw(url, obj, what):
    """
    JSON body 写临时文件再 --data-binary 读，不走命令行参数：
    既避免中文/引号的 shell 转义地狱，也保证是真 UTF-8 字节而不是 \\uXXXX。
    """
    os.makedirs(TMPDIR, mode=0o700, exist_ok=True)
    os.chmod(TMPDIR, 0o700)
    fd, path = tempfile.mkstemp(prefix="request-", suffix=".json", dir=TMPDIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        os.chmod(path, 0o600)
        ok, out = run(["curl", "-sS", "-m", str(TIMEOUT), "-X", "POST",
                       "-H", "Content-Type: application/json; charset=utf-8",
                       "--data-binary", f"@{path}", url])
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    if not ok:
        die(f"{what}：请求发不出去 —— {out[:200]}")
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        die(f"{what}：返回不是 JSON —— {out[:200]}")


def post_json(url, obj, what):
    return check(post_json_raw(url, obj, what), what)


def post_file(url, path, what):
    ok, out = run(["curl", "-sS", "-m", str(TIMEOUT), "-F", f"media=@{path}", url], timeout=TIMEOUT + 30)
    if not ok:
        die(f"{what}：上传失败 —— {out[:200]}")
    try:
        return check(json.loads(out), what)
    except json.JSONDecodeError:
        die(f"{what}：返回不是 JSON —— {out[:200]}")


# ---------------------------------------------------------------- 凭证

def load_config(config_path=None):
    appid = os.environ.get("WECHAT_APPID")
    secret = os.environ.get("WECHAT_APPSECRET")
    candidates = [config_path] if config_path else [DEFAULT_CONFIG, LEGACY_CONFIG]
    conf = next((p for p in candidates if p and os.path.exists(p)), candidates[0])
    if (not appid or not secret) and conf and os.path.exists(conf):
        try:
            with open(conf, encoding="utf-8") as f:
                d = json.load(f)
            appid = appid or d.get("appid")
            secret = secret or d.get("secret") or d.get("appsecret")
            if os.stat(conf).st_mode & 0o077:
                warn(f"{conf} 可被其他用户读取，建议执行：chmod 600 {conf}")
        except (json.JSONDecodeError, OSError) as e:
            die(f"{conf} 读不了：{e}")
    if not appid or not secret:
        die(f"没有凭证。请在 Bot 文件夹之外写入 {conf or DEFAULT_CONFIG}：\n"
            f'    {{"appid": "wx...", "secret": "..."}}\n'
            f"  然后 chmod 600 它。或者设 WECHAT_APPID / WECHAT_APPSECRET 环境变量。")
    return appid, secret


def access_token(force=False):
    """
    用 stable_token 不用 /cgi-bin/token：后者每次调用都签发新 token 并让旧的失效，
    多开一个进程就能把正在用的顶掉；stable_token 在有效期内返回同一个。
    """
    os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
    os.chmod(STATE_DIR, 0o700)
    appid, secret = load_config(CONFIG_PATH)
    now = time.time()
    if not force and os.path.exists(TOKEN_CACHE):
        try:
            with open(TOKEN_CACHE, encoding="utf-8") as f:
                c = json.load(f)
            if c.get("appid") == appid and c.get("expires_at", 0) - 300 > now:   # 留 5 分钟余量
                return c["token"]
        except (json.JSONDecodeError, OSError, KeyError):
            pass

    d = post_json(f"{API}/stable_token", {
        "grant_type": "client_credential",
        "appid": appid,
        "secret": secret,
        "force_refresh": bool(force),
    }, "获取 access_token")

    tok = d.get("access_token")
    if not tok:
        die(f"获取 access_token：返回里没有 access_token —— {d}")
    with open(TOKEN_CACHE, "w", encoding="utf-8") as f:
        json.dump({"appid": appid, "token": tok, "expires_at": now + d.get("expires_in", 7200)}, f)
    os.chmod(TOKEN_CACHE, 0o600)
    return tok


def check_permissions(token):
    """只读检查三个关键接口的调用额度；不会创建、更新或发布内容。"""
    endpoints = [
        ("创建草稿", "/cgi-bin/draft/add"),
        ("正式发布", "/cgi-bin/freepublish/submit"),
        ("群发", "/cgi-bin/message/mass/sendall"),
    ]
    results = []
    for label, path in endpoints:
        data = post_json_raw(
            f"{API}/openapi/quota/get?access_token={token}",
            {"cgi_path": path},
            f"检查{label}权限",
        )
        code = data.get("errcode", 0) if isinstance(data, dict) else -1
        quota = data.get("quota", {}) if isinstance(data, dict) else {}
        allowed = code == 0
        results.append({
            "name": label,
            "cgi_path": path,
            "allowed": allowed,
            "errcode": code,
            "errmsg": data.get("errmsg", "") if isinstance(data, dict) else str(data),
            "daily_limit": quota.get("daily_limit"),
            "used": quota.get("used"),
            "remain": quota.get("remain"),
        })
        message = data.get("errmsg", "") if isinstance(data, dict) else str(data)
        if allowed:
            print(f"  ✓ {label}：可用（今日剩余 {quota.get('remain', '未知')} 次）", file=sys.stderr)
        else:
            print(f"  ✗ {label}：不可用（errcode={code} {message}）", file=sys.stderr)
    print("RESULT " + json.dumps({"permissions": results}, ensure_ascii=False))


# ---------------------------------------------------------------- 图片

def prep_image(src, max_bytes, workdir):
    """
    微信正文图只收 jpg/png 且 <1MB。用 macOS 自带 sips 转格式/压体积，
    这样不用为了一张图去装 Pillow。返回可上传的本地路径。
    """
    os.makedirs(workdir, exist_ok=True)
    ext = os.path.splitext(src)[1].lower()
    size = os.path.getsize(src)

    if ext in (".jpg", ".jpeg", ".png") and size <= max_bytes:
        return src

    # 名字里掺一段源路径的 hash：不同目录下的同名图（a/img.png 与 b/img.png）
    # 否则会压到同一个输出文件上，后一张把前一张覆盖掉
    base = re.sub(r"[^\w.-]", "_", os.path.basename(os.path.splitext(src)[0]))
    tag = f"{zlib.crc32(os.path.abspath(src).encode()) & 0xffffff:06x}"
    for width, quality in ((2000, 90), (1600, 80), (1280, 70), (1080, 60), (900, 45)):
        out = os.path.join(workdir, f"{base}_{tag}_{width}_{quality}.jpg")
        ok, err = run(["sips", "-s", "format", "jpeg",
                       "-s", "formatOptions", str(quality),
                       "-Z", str(width), src, "--out", out], timeout=60)
        if not ok:
            warn(f"sips 处理失败（{os.path.basename(src)}）：{err[:120]}")
            return src
        if os.path.getsize(out) <= max_bytes:
            return out
    warn(f"{os.path.basename(src)} 压到最小仍超过 {max_bytes // 1000}KB，照原样传，可能被拒")
    return out


def resolve_image(src, base_dir, workdir):
    """本地路径直接用；http 图先下下来——外链图片贴进正文一定会被微信屏蔽。"""
    if src.startswith(("http://", "https://")):
        os.makedirs(workdir, exist_ok=True)
        name = re.sub(r"[^\w.-]", "_", src.split("/")[-1].split("?")[0]) or "remote"
        if not os.path.splitext(name)[1]:
            name += ".jpg"
        dst = os.path.join(workdir, f"dl_{name}")
        ok, _ = run(["curl", "-sSL", "-m", "40", "-o", dst, src], timeout=60)
        if not ok or not os.path.exists(dst) or os.path.getsize(dst) == 0:
            warn(f"下不动这张图，跳过：{src[:70]}")
            return None
        return dst
    path = os.path.expanduser(src)
    if not os.path.isabs(path):
        path = os.path.join(base_dir, path)
    if not os.path.exists(path):
        warn(f"图片不存在，跳过：{path}")
        return None
    return path


# ---------------------------------------------------------------- Markdown → 公众号 HTML

def inline(text, ctx):
    """行内元素。先 escape 再套正则——markdown 的标记符不会被 escape 动到。"""
    t = html.escape(text, quote=False)

    def _img(m):
        path = resolve_image(m.group(2).strip(), ctx["base_dir"], ctx["workdir"])
        if not path:
            return ""
        if path not in ctx["images"]:
            ctx["images"][path] = f"%%IMG{len(ctx['images'])}%%"
        return f'<img src="{ctx["images"][path]}" style="{STYLE["img"]}"/>'

    def _link(m):
        label, url = m.group(1), m.group(2).strip()
        # 公众号正文只有指向 mp.weixin.qq.com 的超链接能点，其余一律被剥成纯文本，
        # 所以外链走文末脚注——你引用的英文原文链接全靠这个才留得住。
        if "mp.weixin.qq.com" in url:
            return f'<a href="{url}" style="{STYLE["link"]}">{label}</a>'
        if url not in ctx["links"]:
            ctx["links"].append(url)
        return f'{label}<sup style="{STYLE["sup"]}">[{ctx["links"].index(url) + 1}]</sup>'

    # 顺序要紧：图片先于链接，否则 ![]() 会被链接的正则先吃掉
    t = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)[^)]*\)", _img, t)
    t = re.sub(r"\[([^\]]+)\]\(([^)\s]+)[^)]*\)", _link, t)
    t = re.sub(r"`([^`]+)`", lambda m: f'<code style="{STYLE["code"]}">{m.group(1)}</code>', t)
    t = re.sub(r"==([^=\n]+)==", lambda m: f'<span style="{STYLE["mark"]}">{m.group(1)}</span>', t)
    t = re.sub(r"\*\*([^*]+)\*\*", lambda m: f'<strong style="{STYLE["strong"]}">{m.group(1)}</strong>', t)
    t = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", lambda m: f"<em>{m.group(1)}</em>", t)
    return t


def md_to_html(md, base_dir, workdir):
    # markdown 注释（draft 阶段给你的思路线索写在这里）不进正文
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    ctx = {"links": [], "images": {}, "base_dir": base_dir, "workdir": workdir}
    lines = md.split("\n")
    out, i, n = [], 0, len(lines)

    def is_list(s):
        return bool(re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", s))

    def is_block_start(s):
        st = s.strip()
        return (not st or st.startswith(("#", ">", "```"))
                or is_list(s) or re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", st))

    while i < n:
        raw, s = lines[i], lines[i].strip()

        if not s:
            i += 1
            continue

        if s.startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            body = html.escape("\n".join(buf), quote=False).replace("\n", "<br/>")
            out.append(f'<pre style="{STYLE["pre"]}"><code>{body}</code></pre>')
            continue

        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", s):
            out.append(f'<hr style="{STYLE["hr"]}"/>')
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            # h1 降级：文章标题单独在 front matter 里给，正文里不该再出现一级标题
            key, tag = ("h2", "h2") if len(m.group(1)) <= 2 else ("h3", "h3")
            out.append(f'<{tag} style="{STYLE[key]}">{inline(m.group(2), ctx)}</{tag}>')
            i += 1
            continue

        if s.startswith(">"):
            buf = []
            while i < n and (lines[i].strip().startswith(">") or
                             (buf and lines[i].strip() and not is_block_start(lines[i]))):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]).strip())
                i += 1
            paras, cur = [], []
            for b in buf:
                if b:
                    cur.append(b)
                elif cur:
                    paras.append(" ".join(cur))
                    cur = []
            if cur:
                paras.append(" ".join(cur))
            inner = "".join(f'<p style="{STYLE["quote_p"]}">{inline(p, ctx)}</p>' for p in paras)
            out.append(f'<blockquote style="{STYLE["quote"]}">{inner}</blockquote>')
            continue

        if is_list(raw):
            ordered = bool(re.match(r"^\s*\d+[.)]\s+", raw))
            items = []
            while i < n and is_list(lines[i]):
                items.append(re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", lines[i]).strip())
                i += 1
            tag = "ol" if ordered else "ul"
            lis = "".join(f'<li style="{STYLE["li"]}">{inline(x, ctx)}</li>' for x in items)
            out.append(f'<{tag} style="{STYLE["list"]}">{lis}</{tag}>')
            continue

        buf = [s]
        i += 1
        while i < n and lines[i].strip() and not is_block_start(lines[i]):
            buf.append(lines[i].strip())
            i += 1
        out.append(f'<p style="{STYLE["p"]}">{inline(" ".join(buf), ctx)}</p>')

    if ctx["links"]:
        out.append(f'<h3 style="{STYLE["ref_h"]}">参考链接</h3>')
        for idx, url in enumerate(ctx["links"], 1):
            out.append(f'<p style="{STYLE["ref"]}">[{idx}] {html.escape(url, quote=False)}</p>')

    return "".join(out), ctx


# ---------------------------------------------------------------- 输入

def parse_push_md(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()

    meta, body = {}, text
    m = re.match(r"^\s*---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if m:
        for line in m.group(1).split("\n"):
            if ":" in line and not line.strip().startswith("#"):
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip().strip("'\"")
        body = m.group(2)
    else:
        warn(f"{os.path.basename(path)} 没有 front matter，标题只能从正文首个 # 猜")
        h = re.search(r"^#\s+(.*)$", body, re.M)
        if h:
            meta["title"] = h.group(1).strip()

    if not meta.get("title"):
        die(f"{path} 没有 title —— 标题是必填的。")
    return meta, body


def guard(meta, body, path):
    """在进入草稿箱前做基础内容检查。"""
    name = os.path.basename(path)

    words = len(re.findall(r"[一-鿿]", body))
    if words > 3000:
        warn(f"{name} 中文 {words} 字，超过 3000 红线 —— 完读率会掉，建议砍。")
    elif words < 800:
        print(f"  · {name}：{words} 字（速递体量，正常）", file=sys.stderr)
    else:
        print(f"  · {name}：{words} 字", file=sys.stderr)
    if not meta.get("digest"):
        warn(f"{name} 没写 digest，微信会自动截正文前 54 字当摘要（通常很难看）")
    if not meta.get("cover"):
        warn(f"{name} 没写 cover；真正创建或更新草稿时会停止")


# ---------------------------------------------------------------- 主流程

def build_article(path, token, dry_run):
    meta, body = parse_push_md(path)
    guard(meta, body, path)

    prev_style = apply_theme(meta)
    base_dir = os.path.dirname(os.path.abspath(path))
    workdir = os.path.join(TMPDIR, "img")
    try:
        content, ctx = md_to_html(body, base_dir, workdir)
    finally:
        STYLE.clear(); STYLE.update(prev_style)

    if dry_run:
        for local, ph in ctx["images"].items():
            content = content.replace(ph, "file://" + local)
    else:
        for local, ph in ctx["images"].items():
            up = prep_image(local, IMG_MAX_BYTES, workdir)
            r = post_file(f"{API}/media/uploadimg?access_token={token}", up, f"上传正文图 {os.path.basename(local)}")
            content = content.replace(ph, r["url"])
            print(f"  ✓ 正文图 {os.path.basename(local)}", file=sys.stderr)

    art = {
        "title": meta["title"][:64],
        "author": meta.get("author", ""),
        "digest": meta.get("digest", "")[:120],
        "content": content,
        "content_source_url": meta.get("source_url", ""),
        "need_open_comment": 0 if str(meta.get("open_comment", "1")).lower() in ("0", "false", "no") else 1,
        "only_fans_can_comment": 1 if str(meta.get("fans_only_comment", "0")).lower() in ("1", "true", "yes") else 0,
    }

    cover = meta.get("cover")
    if cover:
        p = resolve_image(cover, base_dir, workdir)
        if not p:
            die(f"{os.path.basename(path)} 的封面不存在或无法下载：{cover}")
        if not dry_run:
            up = prep_image(p, COVER_MAX_BYTES, workdir)
            r = post_file(f"{API}/material/add_material?access_token={token}&type=image",
                          up, "上传封面")
            art["thumb_media_id"] = r["media_id"]
            print(f"  ✓ 封面 {os.path.basename(p)}", file=sys.stderr)
    elif not dry_run:
        die(f"{os.path.basename(path)} 没有 cover。创建或更新公众号草稿必须提供封面图。")

    return art, content


def preview(articles_html, date, outdir):
    """存一份能在浏览器里按手机宽度看的预览，比在后台里反复刷快得多。"""
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"{date}.html")
    parts = "".join(
        f'<hr style="border:0;border-top:2px dashed #ccc;margin:3em 0"/>' + h if idx else h
        for idx, h in enumerate(articles_html))
    with open(path, "w", encoding="utf-8") as f:
        f.write('<!doctype html><meta charset="utf-8"><title>预览</title>'
                '<body style="margin:0;background:#ededed">'
                '<div style="max-width:375px;margin:0 auto;background:#fff;padding:20px 16px;'
                'min-height:100vh;box-shadow:0 0 20px rgba(0,0,0,.08)">'
                + parts + "</div></body>")
    return path


def parse_args():
    parser = argparse.ArgumentParser(description="创建或更新微信公众号草稿；不会正式发布或群发。")
    parser.add_argument("files", nargs="*", metavar="ARTICLE.push.md", help="一篇或多篇文章文件")
    parser.add_argument("--dry-run", action="store_true", help="只生成本地 HTML 预览，不调用微信接口")
    parser.add_argument("--force-token", action="store_true", help="强制刷新 access_token")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="预览文件名日期")
    parser.add_argument("--config", help="凭证 JSON 路径；默认读取用户配置目录，再兼容旧配置")
    parser.add_argument("--preview-dir", default=os.path.join(os.getcwd(), "wechat-preview"),
                        help="HTML 预览输出目录")
    parser.add_argument("--update", metavar="MEDIA_ID", help="更新指定草稿，而不是新建草稿")
    parser.add_argument("--index", type=int, default=0, help="更新多图文草稿的第几篇，默认 0")
    parser.add_argument("--check-permissions", action="store_true",
                        help="只读检查草稿、正式发布和群发接口权限")
    return parser.parse_args()


def main():
    global CONFIG_PATH
    args = parse_args()
    CONFIG_PATH = os.path.expanduser(args.config) if args.config else None

    if args.check_permissions:
        token = access_token(force=args.force_token)
        check_permissions(token)
        return

    files = args.files
    if not files:
        die("请提供至少一个 .push.md 文件；可先加 --dry-run 生成本地预览。")
    if args.update and len(files) != 1:
        die("--update 一次只能更新一篇文章文件。")
    if args.index < 0:
        die("--index 不能小于 0。")
    for f in files:
        if not os.path.exists(f):
            die(f"找不到 {f}")

    print(f"处理 {args.date}（{len(files)} 篇）{' · dry-run' if args.dry_run else ''}", file=sys.stderr)

    token = "" if args.dry_run else access_token(force=args.force_token)

    articles, htmls = [], []
    for f in files:
        art, h = build_article(f, token, args.dry_run)
        articles.append(art)
        htmls.append(h)

    path = preview(htmls, args.date, os.path.abspath(os.path.expanduser(args.preview_dir)))

    if args.dry_run:
        print(f"\n✓ dry-run 完成，没碰任何接口。\n  预览：open {path}\n", file=sys.stderr)
        print("RESULT " + json.dumps({"operation": "dry-run", "preview": path}, ensure_ascii=False))
        return

    if args.update:
        payload = {"media_id": args.update, "index": args.index, "articles": articles[0]}
        post_json(f"{API}/draft/update?access_token={token}", payload, "更新草稿")
        operation = "update"
        media_id = args.update
        print(f"\n✓ 草稿已更新  media_id={media_id} index={args.index}", file=sys.stderr)
    else:
        r = post_json(f"{API}/draft/add?access_token={token}", {"articles": articles}, "新增草稿")
        operation = "create"
        media_id = r.get("media_id", "")
        print(f"\n✓ 草稿已进草稿箱  media_id={media_id or '?'}", file=sys.stderr)
    print(f"  预览：open {path}", file=sys.stderr)
    print("\n本工具只创建或更新草稿，不会正式发布、群发或设置定时。", file=sys.stderr)
    print("RESULT " + json.dumps({"operation": operation, "media_id": media_id,
                                  "index": args.index if args.update else None,
                                  "preview": path}, ensure_ascii=False))


if __name__ == "__main__":
    main()
