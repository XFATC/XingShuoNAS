'''
随便写着玩的,大佬勿喷
警告：用户密码为明文存储，极不安全，请勿拿到生产环境使用
其中前端html为ai优化
本项目所需库下载指令：pip install Flask flask-cors waitress requests

made by XFATC ❤️❤️❤️
'''



from time import perf_counter
print('程序开始运行现在开始导入库')

start = perf_counter() #计时

import os
import json
import socket
import threading
import sys
import shutil
import uuid
import requests
from datetime import datetime
from flask import *
from flask_cors import CORS
from werkzeug.serving import run_simple
from waitress import serve

print('库导入完成，开始加载函数等资源')


# ==================== 基础配置 ====================
CONFIG_FILE = "nas_config.json"
DEFAULT_CONFIG = {
    "site_name": "星硕NAS",
    "share_path": r"D:\NAS_Share",
    "temp_chunk_dir": r"D:\NAS_Temp_Chunks",
    "port": 8683,
    "log_file": "nas.log",
    "announcement_url": "http://text.kt-network.cn/360ffd",
    "announcement_cache_time": 5,
    "users": {
        "admin": "123456",
        "user": "123456"
    }
}
#这里公告用的是我自己的大家可以换成自己的公告地址，或者有能力者删除公告功能，提供了txt和json格式


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

config = load_config()
os.makedirs(config["share_path"], exist_ok=True)

TEMP_CHUNK_DIR = config.get("temp_chunk_dir", r"D:\NAS_Temp_Chunks")
os.makedirs(TEMP_CHUNK_DIR, exist_ok=True)

flask_app = Flask(__name__)
flask_app.secret_key = "cloud_disk_2026_secure"
flask_app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024 * 1024
flask_app.config['REQUEST_BUFFER_SIZE'] = 8 * 1024 * 1024
flask_app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
CORS(flask_app)

# ==================== 公告缓存 ====================
announcement_cache = {
    "content": "",
    "last_update": None
}

def fetch_announcement():
    #从远程文字服务器获取公告内容支持纯文本和JSON格式

    url = config.get("announcement_url", "")
    if not url:
        return ""

    cache_time = config.get("announcement_cache_time", 300)

    # 检查缓存是否有效
    if announcement_cache["last_update"]:
        elapsed = (datetime.now() - announcement_cache["last_update"]).total_seconds()
        if elapsed < cache_time and announcement_cache["content"]:
            return announcement_cache["content"]

    try:
        resp = requests.get(url, timeout=5, headers={
            "User-Agent": "XingShuoNAS/1.0"
        })
        resp.encoding = 'utf-8'

        if resp.status_code == 200:
            text = resp.text.strip()
            #解析JSON
            if text.startswith('{') or text.startswith('['):
                try:
                    data = json.loads(text)
                    if isinstance(data, dict) and 'announcement' in data:
                        text = data['announcement']
                    elif isinstance(data, dict) and 'content' in data:
                        text = data['content']
                    elif isinstance(data, list) and len(data) > 0:
                        text = '\n'.join(data)
                except:
                    pass

            announcement_cache["content"] = text
            announcement_cache["last_update"] = datetime.now()
            return text
        else:
            return announcement_cache["content"]
    except requests.exceptions.RequestException as e:
        print(f"获取公告失败: {e}")
        return announcement_cache["content"]

#======================分割线========================

def fmt_size(byte_num):
    if byte_num < 1024:
        return f"{byte_num} B"
    elif byte_num < 1048576:
        return f"{byte_num/1024:.2f} KB"
    elif byte_num < 1073741824:
        return f"{byte_num/1048576:.2f} MB"
    else:
        return f"{byte_num/1073741824:.2f} GB"

def get_file_info(full_path, is_dir):
    if is_dir:
        return ""
    try:
        size = os.path.getsize(full_path)
        return fmt_size(size)
    except:
        return "未知大小"

def get_type(n):
    e = n.lower().split(".")[-1] if "." in n else ""
    img = ["jpg","jpeg","png","gif","webp","bmp"]
    txt = ["txt","md","py","json","html","css","log"]
    vid = ["mp4","mov","webm","flac","mp3","wav","m4a","avi","mkv"] #这里懒得分开视频和音频了，直接合一块吧
    if e in img: return "image"
    if e in txt: return "text"
    if e in vid: return "video"
    if e == "pdf": return "pdf"
    return "other"

def get_user_root(user):
    return os.path.abspath(os.path.join(config["share_path"], user))

def safe_p(rel, user=None):
    if user is None:
        user = session.get("user")
    if not user or user == "admin":
        return None
    base = get_user_root(user)
    if not rel:
        rel = ""
    full = os.path.abspath(os.path.join(base, rel.replace("/", os.sep)))
    base_abs = os.path.abspath(base)
    if not full.startswith(base_abs):
        return None
    return full

def clean_name(name):
    if not name:
        return ""
    name = name.replace('/', '_').replace('\\', '_')
    name = name.replace('..', '_')
    name = name.strip(' .')
    return name

def get_disk_usage(path):
    try:
        root = os.path.splitdrive(path)[0] + '\\' if os.name == 'nt' else '/'
        usage = shutil.disk_usage(root)
        free = usage.free
        total = usage.total
        used = total - free
        used_percent = (used / total) * 100
        return free, total, used, used_percent
    except:
        return 0, 0, 0, 0

def merge_chunks(file_id, filename, target_dir):
    temp_dir = os.path.join(TEMP_CHUNK_DIR, file_id)
    safe_name = clean_name(filename)
    if not safe_name:
        safe_name = f"file_{uuid.uuid4().hex[:8]}"
    final = os.path.join(target_dir, safe_name)
    counter = 1
    base, ext = os.path.splitext(safe_name)
    while os.path.exists(final):
        safe_name = f"{base}_{counter}{ext}"
        final = os.path.join(target_dir, safe_name)
        counter += 1

    os.makedirs(target_dir, exist_ok=True)

    if not os.path.isdir(temp_dir):
        with open(final, "wb") as f_out:
            pass
        return

    chunk_files = [f for f in os.listdir(temp_dir) if f.startswith("chunk_")]
    if not chunk_files:
        with open(final, "wb") as f_out:
            pass
        shutil.rmtree(temp_dir, ignore_errors=True)
        return

    chunks = sorted(chunk_files, key=lambda x: int(x.split("_")[-1]))
    with open(final, "wb") as f_out:
        for c in chunks:
            p = os.path.join(temp_dir, c)
            if not os.path.isfile(p):
                continue
            with open(p, "rb") as f_in:
                shutil.copyfileobj(f_in, f_out, length=64*1024*1024)
            os.remove(p)
    shutil.rmtree(temp_dir, ignore_errors=True)

import time
from functools import wraps

def get_real_ip():
    try:
        if request.headers.get('X-Forwarded-For'):
            ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
        else:
            ip = request.remote_addr
        return ip
    except RuntimeError:
        return "unknown"

def write_log(operation, user, target="", status="success", detail=""):
    log_file = config.get("log_file", "nas.log")
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    ip = get_real_ip() if 'request' in dir() else "unknown"
    log_line = f"[{timestamp}] [{ip}] [{user}] [{operation}] [{target}] [{status}] {detail}\n"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception as e:
        print(f"日志写入失败: {e}")

# ====================前端html====================
login_html = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{site_name}} - 登录</title>
<style>
* {margin:0;padding:0;box-sizing:border-box;font-family:"Inter","Microsoft Yahei",system-ui,sans-serif;}
body {background: #0b1120;min-height:100vh;display:flex;align-items:center;justify-content:center;}
.login-card {background:#1e293b;border-radius:24px;padding:48px 40px;width:90%;max-width:450px;box-shadow:0 20px 60px rgba(0,0,0,0.6);border:1px solid #334155;}
.title {font-size:28px;color:#f1f5f9;text-align:center;margin-bottom:8px;font-weight:700;letter-spacing:1px;}
.subtitle {color:#94a3b8;text-align:center;margin-bottom:32px;font-size:14px;}
.input-item {margin-bottom:20px;}
.input-item input {width:100%;padding:14px 18px;background:#0f172a;border:1px solid #334155;border-radius:12px;font-size:16px;color:#e2e8f0;transition:0.3s;}
.input-item input:focus {outline:none;border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,0.2);}
.input-item input::placeholder {color:#64748b;}
.login-btn {width:100%;padding:14px;background:#3b82f6;color:#fff;border:none;border-radius:12px;font-size:17px;font-weight:600;cursor:pointer;transition:0.3s;}
.login-btn:hover {background:#2563eb;transform:translateY(-1px);}
.error-tip {color:#ef4444;text-align:center;margin:12px 0;height:24px;font-size:14px;}
</style>
</head>
<body>
<div class="login-card">
    <div class="title">{{site_name}}</div>
    <div class="subtitle">输入账号密码登录</div>
    <form method="post">
        <div class="input-item">
            <input name="user" placeholder="用户名" required>
        </div>
        <div class="input-item">
            <input name="passwd" type="password" placeholder="密码" required>
        </div>
        <div class="error-tip">{{error}}</div>
        <button class="login-btn">立即登录</button>
    </form>
</div>
</body>
</html>
"""

main_html = """
<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{site_name}}</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; user-select: none; -webkit-user-select: none; -moz-user-select: none; -ms-user-select: none;}

  :root {
    --bg: #0b1120;
    --card: #1e293b;
    --card-hover: #2d3a4f;
    --text: #e2e8f0;
    --text-mute: #94a3b8;
    --border: #334155;
    --input-bg: #0f172a;
    --file-hover: #1a2332;
    --sidebar: #0f172a;
    --sidebar-border: #1e293b;
    --btn-outline: #334155;
    --btn-outline-hover: #475569;
    --msg-bg: #1e293b;
    --msg-border: #10b981;
    --msg-text: #d1fae5;
    --announcement-bg: linear-gradient(135deg, #1e293b, #2d3a4f);
    --announcement-border: #3b82f6;
  }

  [data-theme="light"] {
    --bg: #f1f5f9;
    --card: #ffffff;
    --card-hover: #e9edf4;
    --text: #1e293b;
    --text-mute: #64748b;
    --border: #d1d5db;
    --input-bg: #f8fafc;
    --file-hover: #f1f5f9;
    --sidebar: #ffffff;
    --sidebar-border: #e5e7eb;
    --btn-outline: #d1d5db;
    --btn-outline-hover: #b0b8c4;
    --msg-bg: #f0fdf4;
    --msg-border: #22c55e;
    --msg-text: #065f46;
    --announcement-bg: linear-gradient(135deg, #eff6ff, #dbeafe);
    --announcement-border: #3b82f6;
  }

  body {
    background: var(--bg);
    font-family: 'Inter', 'Microsoft Yahei', system-ui, sans-serif;
    color: var(--text);
    height: 100vh;
    overflow: hidden;
    display: flex;
    transition: background 0.25s, color 0.25s, border-color 0.25s;
  }

  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 8px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--text-mute); }

  .sidebar {
    width: 220px;
    background: var(--sidebar);
    border-right: 1px solid var(--sidebar-border);
    height: 100vh;
    padding: 24px 16px;
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
    position: sticky;
    top: 0;
    transition: background 0.25s, border-color 0.25s;
  }
  .logo {
    font-size: 22px;
    font-weight: 700;
    color: var(--text);
    padding: 0 12px 32px 12px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .logo span { background: #3b82f6; font-size: 14px; padding: 2px 10px; border-radius: 6px; color: #fff; }
  .nav-section { flex: 1; }
  .nav-item {
    padding: 10px 16px;
    border-radius: 10px;
    color: var(--text-mute);
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 14px;
    transition: all 0.2s;
    margin-bottom: 4px;
    text-decoration: none;
    font-size: 14px;
    font-weight: 500;
  }
  .nav-item:hover { background: var(--card); color: var(--text); }
  .nav-item.active { background: var(--card); color: var(--text); }
  .nav-item .icon { font-size: 18px; width: 24px; text-align: center; }
  .nav-bottom {
    border-top: 1px solid var(--sidebar-border);
    padding-top: 16px;
    margin-top: 8px;
  }

  .main-content {
    flex: 1;
    overflow-y: auto;
    padding: 24px 32px 32px 32px;
    background: var(--bg);
    height: 100vh;
    transition: background 0.25s;
  }

  .topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 28px;
    flex-wrap: wrap;
    gap: 12px;
  }
  .breadcrumb {
    color: var(--text-mute);
    font-size: 13px;
    background: var(--card);
    padding: 8px 18px;
    border-radius: 30px;
    border: 1px solid var(--border);
    transition: background 0.25s, border-color 0.25s;
  }
  .breadcrumb a { color: #60a5fa; text-decoration: none; }
  .breadcrumb a:hover { text-decoration: underline; }
  .topbar-actions {
    display: flex;
    align-items: center;
    gap: 16px;
  }
  .user-badge {
    background: var(--card);
    padding: 6px 16px 6px 12px;
    border-radius: 30px;
    border: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 13px;
    color: var(--text);
    transition: background 0.25s, border-color 0.25s;
  }
  .user-badge .avatar { background: #3b82f6; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 12px; color: #fff; }
  #themeToggle {
    background: transparent;
    border: none;
    color: var(--text-mute);
    font-size: 20px;
    cursor: pointer;
    padding: 4px 8px;
    border-radius: 30px;
    transition: background 0.2s;
  }
  #themeToggle:hover { background: var(--card); }

  .announcement-card {
    background: var(--announcement-bg);
    border: 1px solid var(--announcement-border);
    border-radius: 16px;
    padding: 14px 20px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 14px;
    transition: background 0.25s, border-color 0.25s;
  }
  .announcement-icon {
    font-size: 24px;
    flex-shrink: 0;
  }
  .announcement-content {
    color: var(--text);
    font-size: 14px;
    line-height: 1.6;
  }
  .announcement-content a {
    color: #60a5fa;
    text-decoration: none;
  }
  .announcement-content a:hover {
    text-decoration: underline;
  }

  .disk-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 16px 20px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    gap: 24px;
    flex-wrap: wrap;
    transition: background 0.25s, border-color 0.25s;
  }
  .disk-stats { display: flex; gap: 24px; flex-wrap: wrap; font-size: 13px; color: var(--text-mute); }
  .disk-stats strong { color: var(--text); font-weight: 600; }
  .disk-bar-wrap { flex: 1; min-width: 140px; }
  .disk-bar-bg { background: var(--input-bg); height: 8px; border-radius: 20px; overflow: hidden; }
  .disk-bar-fill { height: 100%; background: linear-gradient(90deg, #3b82f6, #10b981); width: 0%; border-radius: 20px; transition: width 0.4s; }

  .toolbar {
    display: flex;
    gap: 12px;
    margin-bottom: 20px;
    flex-wrap: wrap;
    align-items: center;
  }
  .btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 18px;
    border-radius: 30px;
    font-size: 13px;
    font-weight: 600;
    border: none;
    cursor: pointer;
    transition: all 0.2s;
    background: var(--card);
    color: var(--text);
    border: 1px solid var(--border);
    text-decoration: none;
  }
  .btn-primary { background: #3b82f6; border-color: #3b82f6; color: #fff; }
  .btn-primary:hover { background: #2563eb; transform: translateY(-1px); box-shadow: 0 8px 16px rgba(59,130,246,0.2); }
  .btn-success { background: #10b981; border-color: #10b981; color: #fff; }
  .btn-success:hover { background: #059669; transform: translateY(-1px); }
  .btn-danger { background: #ef4444; border-color: #ef4444; color: #fff; }
  .btn-danger:hover { background: #dc2626; }
  .btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text); }
  .btn-outline:hover { background: var(--card); }
  .btn-purple { background: #8b5cf6; border-color: #8b5cf6; color: #fff; }
  .btn-purple:hover { background: #7c3aed; transform: translateY(-1px); }

  .file-grid {
    background: var(--card);
    border-radius: 16px;
    border: 1px solid var(--border);
    overflow: hidden;
    transition: background 0.25s, border-color 0.25s;
  }
  .file-header {
    display: grid;
    grid-template-columns: 3fr 1fr 2fr;
    padding: 12px 20px;
    background: var(--input-bg);
    border-bottom: 1px solid var(--border);
    font-size: 12px;
    font-weight: 600;
    color: var(--text-mute);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    transition: background 0.25s, border-color 0.25s;
  }
  .file-row {
    display: grid;
    grid-template-columns: 3fr 1fr 2fr;
    padding: 12px 20px;
    align-items: center;
    border-bottom: 1px solid var(--border);
    transition: background 0.15s;
    cursor: pointer;
  }
  .file-row:last-child { border-bottom: none; }
  .file-row:hover { background: var(--file-hover); }
  .file-row .name { display: flex; align-items: center; gap: 12px; font-size: 14px; font-weight: 500; color: var(--text); }
  .file-row .name a { color: var(--text); text-decoration: none; }
  .file-row .name a:hover { color: #60a5fa; }
  .file-row .size { color: var(--text-mute); font-size: 13px; }
  .file-row .ops { display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap; }
  .file-row .ops .btn { padding: 4px 14px; font-size: 12px; }
  .file-icon { font-size: 20px; width: 32px; text-align: center; }
  .folder-icon { color: #fbbf24; }

  #uploadProgressArea {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 16px 20px;
    margin-top: 16px;
    display: none;
    transition: background 0.25s, border-color 0.25s;
  }
  #totalProgressBar {
    width: 100%; height: 10px; border-radius: 20px; overflow: hidden; appearance: none;
    background: var(--input-bg);
  }
  #totalProgressBar::-webkit-progress-bar { background: var(--input-bg); border-radius: 20px; }
  #totalProgressBar::-webkit-progress-value { background: linear-gradient(90deg, #3b82f6, #10b981); border-radius: 20px; }
  #totalProgressBar::-moz-progress-bar { background: linear-gradient(90deg, #3b82f6, #10b981); border-radius: 20px; }

  .upload-stats {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    color: var(--text-mute);
    margin-top: 10px;
    flex-wrap: wrap;
    gap: 8px;
  }
  .upload-file-name {
    color: var(--text);
    font-weight: 500;
    max-width: 300px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .upload-percent {
    color: var(--text);
    font-weight: 600;
    font-size: 15px;
  }

  .modal-overlay {
    position: fixed; top:0; left:0; width:100%; height:100%;
    background: rgba(0,0,0,0.7); backdrop-filter: blur(6px);
    display: none; align-items: center; justify-content: center;
    z-index: 2000;
  }
  .modal-box {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 24px;
    padding: 32px;
    width: 400px;
    max-width: 92%;
    box-shadow: 0 30px 60px rgba(0,0,0,0.6);
    transition: background 0.25s, border-color 0.25s;
  }
  .modal-box h3 { font-size: 20px; margin-bottom: 20px; color: var(--text); }
  .modal-box .input-group { margin-bottom: 16px; }
  .modal-box .input-group label { display: block; font-size: 13px; color: var(--text-mute); margin-bottom: 4px; }
  .modal-box .input-group input {
    width: 100%; padding: 10px 14px; background: var(--input-bg); border: 1px solid var(--border);
    border-radius: 12px; font-size: 14px; color: var(--text); transition: 0.3s;
  }
  .modal-box .input-group input:focus { outline: none; border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,0.15); }
  .modal-btns { display: flex; gap: 12px; justify-content: flex-end; margin-top: 8px; }
  .msg-banner {
    background: var(--msg-bg);
    border-left: 4px solid var(--msg-border);
    padding: 12px 20px;
    border-radius: 12px;
    margin-bottom: 20px;
    color: var(--msg-text);
    transition: background 0.25s, border-color 0.25s, color 0.25s;
  }

  @media (max-width: 860px) {
    .sidebar { width: 64px; padding: 16px 8px; }
    .sidebar .logo span, .sidebar .nav-item span:not(.icon) { display: none; }
    .sidebar .nav-item { justify-content: center; padding: 12px; }
    .sidebar .logo { justify-content: center; padding-bottom: 20px; }
    .main-content { padding: 16px; }
    .file-header, .file-row { grid-template-columns: 2fr 1fr 1.5fr; }
    .upload-file-name { max-width: 150px; }
  }
  @media (max-width: 600px) {
    .file-header, .file-row { grid-template-columns: 1fr; gap: 6px; }
    .file-row .ops { justify-content: flex-start; }
    .topbar { flex-direction: column; align-items: stretch; }
    .upload-file-name { max-width: 100px; }
    .upload-stats { font-size: 12px; }
    .announcement-card { flex-direction: column; text-align: center; }
  }
</style>
</head>
<body>

<aside class="sidebar">
  <div class="logo">📀 <span>NAS</span></div>
  <div class="nav-section">
    <a href="/" class="nav-item active"><span class="icon">📁</span> <span>文件管理</span></a>
    {% if is_admin %}
    <a href="/admin" class="nav-item"><span class="icon">⚙️</span> <span>用户管理</span></a>
    {% endif %}
    <div class="nav-item" onclick="openPwdModal()"><span class="icon">🔑</span> <span>修改密码</span></div>
  </div>
  <div class="nav-bottom">
    <a href="/logout" class="nav-item"><span class="icon">🚪</span> <span>退出登录</span></a>
  </div>
</aside>

<main class="main-content">
  <div class="topbar">
    <div class="breadcrumb">
      📂 <a href="/">根目录</a>
      {% if current_path %}
        {% set parts = current_path.split('/') %}
        {% for p in parts %}
          {% if p %}
            / <a href="/?path={{ parts[:loop.index]|join('/') }}">{{ p }}</a>
          {% endif %}
        {% endfor %}
      {% endif %}
    </div>
    <div class="topbar-actions">
      <div class="user-badge">
        <span class="avatar">{{ user[0]|upper }}</span>
        {{ user }}
      </div>
      <button id="themeToggle" title="切换主题">🌙</button>
    </div>
  </div>

  {% if msg %}
  <div class="msg-banner">✅ {{ msg }}</div>
  {% endif %}

  {% if announcement %}
  <div class="announcement-card">
    <div class="announcement-icon">📢</div>
    <div class="announcement-content">{{ announcement | safe }}</div>
  </div>
  {% endif %}

  <div class="disk-card">
    <div class="disk-stats">
      <span>📦 已用 <strong>{{ used_space }}</strong></span>
      <span>💾 可用 <strong>{{ free_space }}</strong></span>
      <span>💿 总计 <strong>{{ total_space }}</strong></span>
    </div>
    <div class="disk-bar-wrap">
      <div class="disk-bar-bg">
        <div class="disk-bar-fill" style="width: {{ used_percent }}%;"></div>
      </div>
    </div>
  </div>

  <div class="toolbar">
    <a href="/" class="btn btn-outline">📂 根目录</a>
    <button class="btn btn-primary" onclick="document.getElementById('mkdirInput').style.display='flex';">➕ 新建文件夹</button>
    <form id="mkdirInput" style="display:none;align-items:center;gap:8px;flex-wrap:wrap;" method="post" action="/mkdir">
      <input name="name" placeholder="文件夹名称" required style="background:var(--input-bg);border:1px solid var(--border);border-radius:30px;padding:8px 16px;color:var(--text);font-size:13px;">
      <input type="hidden" name="cur" value="{{current_path}}">
      <button type="submit" class="btn btn-success">创建</button>
      <button type="button" class="btn btn-outline" onclick="this.parentElement.style.display='none';">取消</button>
    </form>

    <input type="file" id="uploadFile" style="display:none;" multiple>
    <button class="btn btn-primary" onclick="document.getElementById('uploadFile').click();">⬆️ 上传文件</button>

    <input type="file" id="uploadFolderInput" style="display:none;" webkitdirectory multiple>
    <button class="btn btn-purple" onclick="document.getElementById('uploadFolderInput').click();">📁 上传文件夹</button>

    <button id="resumeUploadBtn" class="btn btn-success" style="display:none;">↻ 恢复上次上传</button>
    <button id="cancelUploadBtn" class="btn btn-danger" style="display:none;" onclick="cancelUpload()">⏹ 取消上传</button>
  </div>

  <div id="uploadProgressArea">
    <progress id="totalProgressBar" value="0" max="100"></progress>
    <div class="upload-stats">
      <span>📄 <span id="currentUploadFile" class="upload-file-name">-</span></span>
      <span class="upload-percent" id="uploadPercent">0%</span>
      <span>⚡ <span id="instantSpeed">--</span> / 📊 <span id="avgSpeed">--</span></span>
    </div>
    <div class="upload-stats" style="margin-top:2px;font-size:12px;">
      <span id="uploadStatusMsg">准备就绪</span>
      <span id="folderProgress"></span>
    </div>
  </div>
  <div id="uploadStatus" style="margin:8px 0;font-size:13px;color:var(--text-mute);"></div>

  <div class="file-grid">
    <div class="file-header">
      <span>名称</span>
      <span>大小</span>
      <span style="text-align:right;">操作</span>
    </div>

    {% if current_path != "" %}
    <div class="file-row" onclick="window.location.href='/?path={{ parent_path }}'">
      <div class="name"><span class="file-icon"></span> 返回上一级</div>
      <div class="size">-</div>
      <div class="ops"></div>
    </div>
    {% endif %}

    {% for name,isdir,size_text in items %}
    {% set fp = current_path + '/' + name if current_path else name %}
    <div class="file-row" {% if isdir %}onclick="window.location.href='/?path={{ fp }}'"{% endif %}>
      <div class="name">
        <span class="file-icon {% if isdir %}folder-icon{% endif %}">{% if isdir %}📁{% else %}📄{% endif %}</span>
        {% if isdir %}
          <a href="/?path={{ fp }}">{{ name }}</a>
        {% else %}
          {{ name }}
        {% endif %}
      </div>
      <div class="size">{% if not isdir %}{{ size_text }}{% endif %}</div>
      <div class="ops" onclick="event.stopPropagation();">
        {% if not isdir %}
          <a href="/preview?path={{ fp }}" class="btn btn-outline">预览</a>
          <a href="/download?path={{ fp }}" class="btn btn-outline">下载</a>
        {% endif %}
        <button class="btn btn-danger" onclick="openDelPop('{{ fp }}','{{ name }}')">删除</button>
      </div>
    </div>
    {% endfor %}
  </div>
</main>

<div class="modal-overlay" id="delModal">
  <div class="modal-box">
    <h3>⚠️ 确认删除</h3>
    <p style="color:var(--text-mute);margin-bottom:24px;">确定要删除 <strong id="delFileName" style="color:var(--text);"></strong> 吗？此操作不可恢复。</p>
    <div class="modal-btns">
      <button class="btn btn-outline" onclick="closeDelPop()">取消</button>
      <form id="delForm" action="/del" method="post" style="margin:0;">
        <input type="hidden" name="target" id="delTarget">
        <button type="submit" class="btn btn-danger" id="sureDelBtn" disabled>请冷静3秒</button>
      </form>
    </div>
  </div>
</div>

<div class="modal-overlay" id="pwdModal">
  <div class="modal-box">
    <h3>🔑 修改密码</h3>
    <form id="changePwdForm" action="/change_password_self" method="post">
      <div class="input-group">
        <label>旧密码</label>
        <input type="password" name="old_password" required placeholder="请输入当前密码">
      </div>
      <div class="input-group">
        <label>新密码</label>
        <input type="password" name="new_password" required placeholder="请输入新密码">
      </div>
      <div class="input-group">
        <label>确认新密码</label>
        <input type="password" name="confirm_password" required placeholder="请再次输入新密码">
      </div>
      <div class="modal-btns">
        <button type="button" class="btn btn-outline" onclick="closePwdModal()">取消</button>
        <button type="submit" class="btn btn-primary">确认修改</button>
      </div>
    </form>
    <div id="pwdModalMsg" style="color:#ef4444;margin-top:12px;font-size:14px;"></div>
  </div>
</div>

<script>
const themeBtn = document.getElementById('themeToggle');
const html = document.documentElement;

function loadTheme() {
  const saved = localStorage.getItem('nas_theme');
  if (saved === 'light') {
    html.setAttribute('data-theme', 'light');
    themeBtn.textContent = '☀️浅色';
  } else {
    html.setAttribute('data-theme', 'dark');
    themeBtn.textContent = '🌙深色';
  }
}

themeBtn.addEventListener('click', () => {
  const isDark = html.getAttribute('data-theme') === 'dark';
  if (isDark) {
    html.setAttribute('data-theme', 'light');
    localStorage.setItem('nas_theme', 'light');
    themeBtn.textContent = '☀️浅色';
  } else {
    html.setAttribute('data-theme', 'dark');
    localStorage.setItem('nas_theme', 'dark');
    themeBtn.textContent = '🌙深色';
  }
  themeBtn.animate([{ transform: 'scale(0.85)' }, { transform: 'scale(1)' }], { duration: 180, easing: 'ease-out' });
});
window.addEventListener('DOMContentLoaded', loadTheme);

function openPwdModal() {
    document.getElementById('pwdModal').style.display = 'flex';
    document.getElementById('pwdModalMsg').innerText = '';
    document.getElementById('changePwdForm').reset();
}
function closePwdModal() {
    document.getElementById('pwdModal').style.display = 'none';
}
document.getElementById('pwdModal').addEventListener('click', function(e) {
    if (e.target === this) closePwdModal();
});

let delTimer = null;
function openDelPop(target, fname) {
    const modal = document.getElementById('delModal');
    document.getElementById('delTarget').value = target;
    document.getElementById('delFileName').innerText = fname;
    const sureBtn = document.getElementById('sureDelBtn');
    clearInterval(delTimer);
    modal.style.display = 'flex';
    sureBtn.disabled = true;
    let sec = 3;
    sureBtn.innerText = `冷静 ${sec}s`;
    delTimer = setInterval(() => {
        sec--;
        sureBtn.innerText = `冷静 ${sec}s`;
        if (sec <= 0) {
            clearInterval(delTimer);
            sureBtn.disabled = false;
            sureBtn.innerText = '删除';
        }
    }, 1000);
}
function closeDelPop() {
    clearInterval(delTimer);
    document.getElementById('delModal').style.display = 'none';
}
document.getElementById('delModal').addEventListener('click', function(e) {
    if (e.target === this) closeDelPop();
});

// ===== 上传逻辑 =====
const CHUNK_SIZE = 64 * 1024 * 1024;
const STORAGE_KEY = 'nas_upload_task';
let uploading = false;
let uploadCancelled = false;
let currentTask = null;
let folderFileList = [];
let folderTotalFiles = 0;
let folderCompletedFiles = 0;
let isFolderMode = false;

const fileInput = document.getElementById('uploadFile');
const folderInput = document.getElementById('uploadFolderInput');
const resumeBtn = document.getElementById('resumeUploadBtn');
const cancelBtn = document.getElementById('cancelUploadBtn');

let uploadStartTime = null;
let totalUploadedBytes = 0;
let lastChunkTime = null;
let lastChunkBytes = 0;

const totalProgressBar = document.getElementById('totalProgressBar');

function formatSpeed(bytesPerSec) {
    if (bytesPerSec < 1024) return `${bytesPerSec.toFixed(0)} B/s`;
    if (bytesPerSec < 1048576) return `${(bytesPerSec / 1024).toFixed(1)} KB/s`;
    return `${(bytesPerSec / 1048576).toFixed(1)} MB/s`;
}

function updateSpeedDisplay() {
    if (!uploadStartTime) return;
    const now = Date.now();
    const totalElapsed = (now - uploadStartTime) / 1000;
    const avgSpeed = totalElapsed > 0 ? totalUploadedBytes / totalElapsed : 0;
    document.getElementById('avgSpeed').innerText = formatSpeed(avgSpeed);
    if (lastChunkTime && lastChunkBytes > 0) {
        const chunkElapsed = (now - lastChunkTime) / 1000;
        const instant = chunkElapsed > 0 ? lastChunkBytes / chunkElapsed : 0;
        document.getElementById('instantSpeed').innerText = formatSpeed(instant);
    } else {
        document.getElementById('instantSpeed').innerText = formatSpeed(avgSpeed);
    }
}

function resetSpeedStats() {
    uploadStartTime = null; totalUploadedBytes = 0; lastChunkTime = null; lastChunkBytes = 0;
    document.getElementById('instantSpeed').innerText = '--';
    document.getElementById('avgSpeed').innerText = '--';
}

function saveTask(task) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
        fileId: task.fileId, fileName: task.fileName, currentPath: task.currentPath,
        totalChunks: task.totalChunks, uploadedChunks: task.uploadedChunks,
        isFolder: task.isFolder || false,
        folderRelativePath: task.folderRelativePath || ''
    }));
}
function clearTask() { localStorage.removeItem(STORAGE_KEY); resumeBtn.style.display = 'none'; }
function loadPendingTask() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return null;
        const task = JSON.parse(raw);
        if (task.currentPath === '{{ current_path }}') return task;
        clearTask(); return null;
    } catch(e) { clearTask(); return null; }
}

function showResumeButton() {
    const task = loadPendingTask();
    if (task && task.totalChunks > 0 && task.uploadedChunks.length < task.totalChunks) {
        resumeBtn.style.display = 'inline-block';
        resumeBtn.onclick = () => promptResume(task);
    } else { resumeBtn.style.display = 'none'; }
}

async function promptResume(pendingTask) {
    if (uploading) { alert('已有上传任务进行中'); return; }
    const input = document.createElement('input');
    input.type = 'file';
    input.webkitdirectory = pendingTask.isFolder || false;
    input.multiple = true;
    input.onchange = async (e) => {
        const files = e.target.files;
        if (!files || files.length === 0) return;
        let targetFile = null;
        let targetPath = pendingTask.folderRelativePath || '';
        for (let f of files) {
            let relPath = f.webkitRelativePath || f.name;
            if (relPath === pendingTask.fileName || f.name === pendingTask.fileName) {
                targetFile = f;
                targetPath = relPath;
                break;
            }
        }
        if (!targetFile) {
            alert(`请选择上次未完成上传的文件: ${pendingTask.fileName}`);
            return;
        }
        const checkResp = await fetch('/api/chunk/check', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fileId: pendingTask.fileId })
        });
        const checkResult = await checkResp.json();
        if (checkResult.code === 200) {
            pendingTask.uploadedChunks = checkResult.uploaded_chunks || [];
            saveTask(pendingTask);
        }
        startUploadTask({ ...pendingTask, fileObject: targetFile, folderRelativePath: targetPath });
    };
    input.click();
}

function updateTotalProgress(pct, statusMsg, fileProgress) {
    totalProgressBar.value = pct;
    document.getElementById('uploadPercent').innerText = pct + '%';
    if (statusMsg) {
        document.getElementById('uploadStatusMsg').innerText = statusMsg;
    }
    if (isFolderMode && folderTotalFiles > 0) {
        document.getElementById('folderProgress').innerText = `📊 ${folderCompletedFiles}/${folderTotalFiles}`;
    } else if (fileProgress !== undefined) {
        document.getElementById('folderProgress').innerText = `📊 文件 ${fileProgress}%`;
    } else {
        document.getElementById('folderProgress').innerText = '';
    }
}

async function startUploadTask(task) {
    if (uploading) return;
    if (uploadCancelled) {
        uploadCancelled = false;
        return;
    }
    uploading = true;
    currentTask = task;
    const { fileId, fileName, currentPath, totalChunks, uploadedChunks: initialUploaded, fileObject: file, folderRelativePath } = task;
    let completedChunks = initialUploaded.length;
    const progressArea = document.getElementById('uploadProgressArea');
    const statusDiv = document.getElementById('uploadStatus');
    const currentFileSpan = document.getElementById('currentUploadFile');

    if (folderRelativePath) {
        currentFileSpan.innerText = folderRelativePath;
    } else {
        currentFileSpan.innerText = fileName;
    }

    progressArea.style.display = 'block';
    resumeBtn.style.display = 'none';
    cancelBtn.style.display = 'inline-block';

    if (isFolderMode && folderTotalFiles > 0) {
        const pct = Math.floor((folderCompletedFiles / folderTotalFiles) * 100);
        updateTotalProgress(pct, '上传中...');
    } else {
        updateTotalProgress(0, '上传中...');
    }

    if (!uploadStartTime) {
        resetSpeedStats();
        uploadStartTime = Date.now();
        totalUploadedBytes = completedChunks * CHUNK_SIZE;
        if (totalUploadedBytes > file.size) totalUploadedBytes = file.size;
        lastChunkTime = uploadStartTime;
        lastChunkBytes = 0;
    }

    if (!file) {
        updateTotalProgress(0, '❌ 文件对象丢失');
        resetUploadUI();
        return;
    }

    for (let i = 0; i < totalChunks; i++) {
        if (uploadCancelled) {
            updateTotalProgress(0, '⏹ 已取消');
            resetUploadUI();
            return;
        }
        if (task.uploadedChunks.includes(i)) continue;
        const start = i * CHUNK_SIZE;
        const end = Math.min(start + CHUNK_SIZE, file.size);
        const chunkSize = end - start;
        const chunk = file.slice(start, end);
        const formData = new FormData();
        formData.append('fileId', fileId);
        formData.append('index', i);
        formData.append('chunk', chunk);
        try {
            const resp = await fetch('/api/chunk', { method: 'POST', body: formData });
            if (!resp.ok) throw new Error('分块上传失败');
            lastChunkBytes = chunkSize;
            lastChunkTime = Date.now();
            totalUploadedBytes += chunkSize;
            updateSpeedDisplay();
            completedChunks++;
            task.uploadedChunks.push(i);
            saveTask(task);

            const filePct = Math.floor((completedChunks / totalChunks) * 100);

            if (isFolderMode && folderTotalFiles > 0) {
                const totalPct = Math.floor((folderCompletedFiles / folderTotalFiles) * 100);
                updateTotalProgress(totalPct, `上传中... ${folderCompletedFiles}/${folderTotalFiles}`, filePct);
            } else {
                updateTotalProgress(filePct, `上传中... ${filePct}%`);
            }
        } catch (err) {
            updateTotalProgress(0, '❌ 上传失败');
            statusDiv.innerHTML = `❌ 上传失败: ${err.message}`;
            if (isFolderMode) {
                folderCompletedFiles++;
                uploading = false;
                cancelBtn.style.display = 'none';
                uploadNextFileInFolder();
                return;
            } else {
                resetUploadUI();
                return;
            }
        }
    }

    if (isFolderMode && folderTotalFiles > 0) {
        const totalPct = Math.floor((folderCompletedFiles / folderTotalFiles) * 100);
        updateTotalProgress(totalPct, '合并中...');
    } else {
        updateTotalProgress(100, '合并中...');
    }

    try {
        const mergeResp = await fetch('/api/merge', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fileId, name: fileName, cur: currentPath })
        });
        const result = await mergeResp.json();
        if (result.code === 200) {
            clearTask();
            if (isFolderMode) {
                folderCompletedFiles++;
                const total = folderTotalFiles;
                const done = folderCompletedFiles;
                const pct = total > 0 ? Math.floor((done / total) * 100) : 0;
                updateTotalProgress(pct, `✅ 已上传 ${done}/${total} 个文件`);
                uploading = false;
                cancelBtn.style.display = 'none';
                setTimeout(() => uploadNextFileInFolder(), 300);
            } else {
                updateTotalProgress(100, '✅ 上传成功！');
                uploading = false;
                setTimeout(() => location.reload(), 1000);
            }
        } else {
            throw new Error(result.msg || '合并失败');
        }
    } catch (err) {
        updateTotalProgress(0, '❌ 合并失败');
        statusDiv.innerHTML = `❌ 合并失败: ${err.message}`;
        if (isFolderMode) {
            folderCompletedFiles++;
            uploading = false;
            cancelBtn.style.display = 'none';
            uploadNextFileInFolder();
        } else {
            resetUploadUI();
        }
    }
}

function resetUploadUI() {
    uploading = false;
    uploadCancelled = false;
    isFolderMode = false;
    cancelBtn.style.display = 'none';
    fileInput.value = '';
    folderInput.value = '';
    setTimeout(() => {
        const pa = document.getElementById('uploadProgressArea');
        if (pa) pa.style.display = 'none';
        resetSpeedStats();
    }, 3000);
}

function cancelUpload() {
    if (confirm('确定要取消当前上传任务吗？')) {
        uploadCancelled = true;
        uploading = false;
        updateTotalProgress(0, '⏹ 已取消');
        cancelBtn.style.display = 'none';
    }
}

function collectFilesFromFolder(fileList) {
    const result = [];
    for (let i = 0; i < fileList.length; i++) {
        const f = fileList[i];
        const relPath = f.webkitRelativePath || f.name;
        result.push({
            file: f,
            relativePath: relPath,
            fileName: f.name,
            size: f.size
        });
    }
    result.sort((a, b) => a.relativePath.localeCompare(b.relativePath));
    return result;
}

async function startFolderUpload(fileList) {
    if (uploading) { alert('已有上传任务进行中'); return; }
    if (!fileList || fileList.length === 0) return;

    isFolderMode = true;
    const files = collectFilesFromFolder(fileList);
    folderTotalFiles = files.length;
    folderCompletedFiles = 0;
    folderFileList = files;

    document.getElementById('uploadProgressArea').style.display = 'block';
    updateTotalProgress(0, `准备上传 (${folderTotalFiles} 个文件)`);
    document.getElementById('folderProgress').innerText = `📊 0/${folderTotalFiles}`;

    uploadNextFileInFolder();
}

function uploadNextFileInFolder() {
    if (uploadCancelled) {
        updateTotalProgress(0, '⏹ 已取消');
        cancelBtn.style.display = 'none';
        return;
    }

    const nextIndex = folderCompletedFiles;
    if (nextIndex >= folderTotalFiles) {
        updateTotalProgress(100, '✅ 文件夹上传完成！');
        setTimeout(() => location.reload(), 1500);
        return;
    }

    const item = folderFileList[nextIndex];
    const file = item.file;
    const relPath = item.relativePath;

    const pathParts = relPath.split('/');
    const fileName = pathParts.pop();
    const subDir = pathParts.join('/');

    const displayPath = subDir ? `${subDir}/${fileName}` : fileName;

    const basePath = '{{ current_path }}';
    let targetPath = basePath;
    if (subDir) {
        targetPath = basePath ? basePath + '/' + subDir : subDir;
    }

    const fileId = crypto.randomUUID ? crypto.randomUUID() : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => (Math.random()*16|0).toString(16));
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);

    const task = {
        fileId: fileId,
        fileName: fileName,
        currentPath: targetPath,
        totalChunks: totalChunks,
        uploadedChunks: [],
        fileObject: file,
        isFolder: true,
        folderRelativePath: displayPath
    };

    saveTask(task);
    document.getElementById('currentUploadFile').innerText = displayPath;
    startUploadTask(task);
}

fileInput.addEventListener('change', async () => {
    if (uploading) { alert('已有上传任务进行中'); return; }
    const files = fileInput.files;
    if (!files || files.length === 0) return;

    if (files.length > 1) {
        isFolderMode = true;
        let completed = 0;
        const total = files.length;
        folderTotalFiles = total;
        folderCompletedFiles = 0;
        const fileList = [];
        for (let i = 0; i < files.length; i++) {
            fileList.push({
                file: files[i],
                relativePath: files[i].name,
                fileName: files[i].name,
                size: files[i].size
            });
        }
        fileList.sort((a, b) => a.relativePath.localeCompare(b.relativePath));
        folderFileList = fileList;

        document.getElementById('uploadProgressArea').style.display = 'block';
        updateTotalProgress(0, `准备上传 ${total} 个文件`);
        document.getElementById('folderProgress').innerText = `📊 0/${total}`;

        for (let i = 0; i < fileList.length; i++) {
            if (uploadCancelled) break;
            const item = fileList[i];
            const file = item.file;
            const fileId = crypto.randomUUID ? crypto.randomUUID() : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => (Math.random()*16|0).toString(16));
            const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
            const task = {
                fileId, fileName: file.name, currentPath: '{{ current_path }}',
                totalChunks, uploadedChunks: [], fileObject: file,
                isFolder: true,
                folderRelativePath: file.name
            };
            document.getElementById('currentUploadFile').innerText = file.name;
            await new Promise((resolve) => {
                startUploadTask(task);
                const checkDone = setInterval(() => {
                    if (!uploading || folderCompletedFiles > completed) {
                        clearInterval(checkDone);
                        completed++;
                        const pct = Math.floor((completed / total) * 100);
                        updateTotalProgress(pct, `已上传 ${completed}/${total}`);
                        document.getElementById('folderProgress').innerText = `📊 ${completed}/${total}`;
                        resolve();
                    }
                }, 500);
            });
        }
        updateTotalProgress(100, '✅ 全部上传完成！');
        setTimeout(() => location.reload(), 1500);
        return;
    }

    isFolderMode = false;
    const file = files[0];
    const pending = loadPendingTask();
    if (pending && pending.fileName === file.name && pending.currentPath === '{{ current_path }}') {
        if (confirm('检测到该文件上次未完成上传，是否继续？')) {
            const checkResp = await fetch('/api/chunk/check', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ fileId: pending.fileId })
            });
            const checkResult = await checkResp.json();
            if (checkResult.code === 200) {
                pending.uploadedChunks = checkResult.uploaded_chunks || [];
                saveTask(pending);
            }
            startUploadTask({ ...pending, fileObject: file });
            return;
        } else clearTask();
    }
    const fileId = crypto.randomUUID ? crypto.randomUUID() : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => (Math.random()*16|0).toString(16));
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
    const newTask = {
        fileId, fileName: file.name, currentPath: '{{ current_path }}',
        totalChunks, uploadedChunks: [], fileObject: file,
        isFolder: false
    };
    saveTask(newTask);
    startUploadTask(newTask);
});

folderInput.addEventListener('change', async () => {
    if (uploading) { alert('已有上传任务进行中'); return; }
    const files = folderInput.files;
    if (!files || files.length === 0) return;
    uploadCancelled = false;
    cancelBtn.style.display = 'inline-block';
    await startFolderUpload(files);
});

window.addEventListener('DOMContentLoaded', showResumeButton);
</script>
</body>
</html>
"""

# ==================== 大文件上传API ====================
@flask_app.route("/api/chunk", methods=["POST"])
def api_chunk():
    if "user" not in session:
        return jsonify({"code":403, "msg":"未登录"})
    if session["user"] == "admin":
        return jsonify({"code":403, "msg":"管理员不能上传"})
    file_id = request.form.get("fileId")
    index = request.form.get("index")
    chunk = request.files.get("chunk")
    d = os.path.join(TEMP_CHUNK_DIR, file_id)
    os.makedirs(d, exist_ok=True)
    chunk.save(os.path.join(d, f"chunk_{index}"))
    return jsonify({"code":200})

@flask_app.route("/api/merge", methods=["POST"])
def api_merge():
    if "user" not in session:
        return jsonify({"code":403, "msg":"未登录"})
    if session["user"] == "admin":
        return jsonify({"code":403, "msg":"管理员不能上传"})
    data = request.json
    file_id = data.get("fileId")
    name = data.get("name")
    cur = data.get("cur")
    if cur:
        cur = cur.strip().lstrip('/')
    target_dir = safe_p(cur)
    if not target_dir:
        return jsonify({"code":403, "msg": f"无效路径: {cur}"})
    try:
        merge_chunks(file_id, name, target_dir)
        write_log("upload", session["user"], target=os.path.join(cur, name), status="success", detail="上传文件")
        return jsonify({"code":200, "msg": "合并成功"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"code":500, "msg": f"合并失败: {str(e)}"})

@flask_app.route("/api/chunk/check", methods=["POST"])
def api_chunk_check():
    if "user" not in session:
        return jsonify({"code":403, "msg":"未登录"})
    if session["user"] == "admin":
        return jsonify({"code":403, "msg":"管理员不能上传"})
    data = request.json
    file_id = data.get("fileId")
    if not file_id:
        return jsonify({"code":400, "msg":"缺少 fileId"})
    temp_dir = os.path.join(TEMP_CHUNK_DIR, file_id)
    if not os.path.isdir(temp_dir):
        return jsonify({"code":200, "uploaded_chunks": []})
    chunks = []
    for fname in os.listdir(temp_dir):
        if fname.startswith("chunk_"):
            try:
                idx = int(fname.split("_")[-1])
                chunks.append(idx)
            except:
                pass
    return jsonify({"code":200, "uploaded_chunks": chunks})

# ==================== Flask路由 ====================
@flask_app.route("/login", methods=["GET", "POST"])
def login():
    err = ""
    if request.method == "POST":
        u = request.form.get("user","")
        p = request.form.get("passwd","")
        if u in config["users"] and config["users"][u] == p:
            session["user"] = u
            write_log("login", u, status="success", detail="登录成功")
            if u != "admin":
                os.makedirs(get_user_root(u), exist_ok=True)
            if u == "admin":
                return redirect("/admin")
            else:
                return redirect("/")
        err = "用户名或密码错误"
        write_log("login", u, status="fail", detail="密码错误")
    return render_template_string(login_html, site_name=config["site_name"], error=err)

@flask_app.route("/logout")
def logout():
    write_log("logout", session.get("user","unknown"), status="success", detail="退出登录")
    session.clear()
    return redirect("/login")

@flask_app.route("/")
def index():
    if "user" not in session:
        return redirect("/login")
    user = session["user"]
    if user == "admin":
        return redirect("/admin")
    cur = request.args.get("path","")
    full = safe_p(cur)
    if not full or not os.path.isdir(full):
        full = get_user_root(user)
        cur = ""
    items = []
    for n in os.listdir(full):
        item_full = os.path.join(full, n)
        isdir = os.path.isdir(item_full)
        size_text = get_file_info(item_full, isdir)
        items.append((n, isdir, size_text))
    items.sort(key=lambda x:not x[1])
    parent = os.path.dirname(cur).replace("\\","/") if cur else ""
    if cur and parent == ".":
        parent = ""

    msg = request.args.get("msg", "")

    free_bytes, total_bytes, used_bytes, used_percent = get_disk_usage(get_user_root(user))
    free_space = fmt_size(free_bytes)
    total_space = fmt_size(total_bytes)
    used_space = fmt_size(used_bytes)

    # 获取公告
    announcement = fetch_announcement()

    return render_template_string(main_html,
        site_name=config["site_name"], user=user,
        is_admin=False,
        current_path=cur, items=items, parent_path=parent,
        free_space=free_space, total_space=total_space, used_space=used_space,
        used_percent=round(used_percent, 1), msg=msg,
        announcement=announcement)

@flask_app.route("/mkdir", methods=["POST"])
def mkdir():
    if "user" not in session:
        return redirect("/login")
    if session["user"] == "admin":
        return redirect("/admin")
    n = request.form.get("name", "")
    n = clean_name(n)
    cur = request.form.get("cur", "")
    if not n:
        return redirect(f"/?path={cur}")
    full = safe_p(os.path.join(cur, n))
    if full:
        os.makedirs(full, exist_ok=True)
        write_log("mkdir", session["user"], target=os.path.join(cur, n), status="success", detail="创建文件夹")
    return redirect(f"/?path={cur}")

@flask_app.route("/upload", methods=["POST"])
def upload():
    if "user" not in session:
        return redirect("/login")
    if session["user"] == "admin":
        return redirect("/admin")
    f = request.files.get("upfile")
    cur = request.form.get("cur", "")
    full = safe_p(cur)
    if f and full:
        filename = clean_name(f.filename)
        if not filename:
            filename = f"file_{uuid.uuid4().hex[:8]}"
        save_path = os.path.join(full, filename)
        counter = 1
        name_without_ext, ext = os.path.splitext(filename)
        while os.path.exists(save_path):
            new_filename = f"{name_without_ext}_{counter}{ext}"
            save_path = os.path.join(full, new_filename)
            counter += 1
        f.save(save_path)
    return redirect(f"/?path={cur}")

@flask_app.route("/download")
def download():
    if "user" not in session:
        return redirect("/login")
    if session["user"] == "admin":
        return redirect("/admin")
    p = request.args.get("path","")
    f = safe_p(p)
    if f and os.path.isfile(f):
        return send_file(f, as_attachment=True, conditional=True, max_age=0)
    return redirect("/")

@flask_app.route("/del", methods=["POST"])
def del_file():
    if "user" not in session:
        return redirect("/login")
    if session["user"] == "admin":
        return redirect("/admin")
    t = request.form.get("target","")
    f = safe_p(t)
    if f:
        if os.path.isdir(f):
            shutil.rmtree(f, ignore_errors=True)
            write_log("delete", session["user"], target=t, status="success", detail="删除文件夹")
        elif os.path.isfile(f):
            os.remove(f)
            write_log("delete", session["user"], target=t, status="success", detail="删除文件")
    return redirect("/")

@flask_app.route("/preview")
def preview():
    if "user" not in session:
        return redirect("/login")
    if session["user"] == "admin":
        return redirect("/admin")
    p = request.args.get("path","")
    f = safe_p(p)
    if not f or not os.path.isfile(f): return redirect("/")
    n = os.path.basename(f)
    t = get_type(n)
    content = ""
    if t == "text":
        try:
            with open(f, "r", encoding="utf-8") as fp:
                content = fp.read()
        except:
            content = "抱歉还没适配这个格式的文件，无法预览"
    back = "/?path=" + os.path.dirname(p).replace("\\","/")
    return render_template_string(preview_html, name=n, path=p, t=t, content=content, back=back)

preview_html = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>预览 - {{name}}</title>
<style>
* {margin:0;padding:0;box-sizing:border-box;font-family:"Inter","Microsoft Yahei",system-ui;}
body {background:#0b1120;padding:24px;color:#e2e8f0;}
.preview-box {max-width:1100px;margin:0 auto;background:#1e293b;border-radius:24px;padding:32px;border:1px solid #334155;}
.operate {margin-bottom:24px;display:flex;gap:12px;flex-wrap:wrap;}
.btn {padding:10px 20px;border-radius:12px;text-decoration:none;font-size:14px;font-weight:600;border:none;cursor:pointer;}
.btn-back {background:#334155;color:#e2e8f0;}
.btn-back:hover {background:#475569;}
.btn-download {background:#3b82f6;color:#fff;}
.btn-download:hover {background:#2563eb;}
h3 {margin-bottom:20px;color:#f1f5f9;}
.img-view {max-width:100%;border-radius:12px;}
.txt-view {background:#0f172a;padding:20px;border-radius:12px;white-space:pre-wrap;max-height:70vh;overflow:auto;border:1px solid #1e293b;color:#e2e8f0;}
video,iframe {width:100%;border-radius:12px;min-height:60vh;background:#0f172a;}
</style>
</head>
<body>
<div class="preview-box">
    <div class="operate">
        <a href="{{back}}" class="btn btn-back">← 返回列表</a>
        <a href="/download?path={{path}}" class="btn btn-download">下载文件</a>
    </div>
    <h3>{{name}}</h3>
    {% if t=='image' %}
        <img src="/raw?path={{path}}" class="img-view">
    {% elif t=='text' %}
        <div class="txt-view">{{content}}</div>
    {% elif t=='video' %}
        <video controls><source src="/raw?path={{path}}"></video>
    {% elif t=='pdf' %}
        <iframe src="/raw?path={{path}}"></iframe>
    {% else %}
        <p style="color:#94a3b8;">抱歉还没适配这个格式的文件，无法预览</p>
    {% endif %}
</div>
</body>
</html>
"""

@flask_app.route("/raw")
def raw():
    if "user" not in session:
        return redirect("/login")
    if session["user"] == "admin":
        return redirect("/admin")
    f = safe_p(request.args.get("path",""))
    if f and os.path.isfile(f):
        return send_file(f, as_attachment=False)
    return "文件不存在",404

@flask_app.route("/admin")
def admin():
    if session.get("user") != "admin":
        return redirect("/")
    return render_template_string(admin_html, users=config["users"], msg=request.args.get("msg",""))

admin_html = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>用户管理</title>
<style>
* {margin:0;padding:0;box-sizing:border-box;font-family:"Inter","Microsoft Yahei",system-ui;}
body {background:#0b1120;color:#e2e8f0;display:flex;height:100vh;overflow:hidden;}
.sidebar {width:220px;background:#0f172a;border-right:1px solid #1e293b;padding:24px 16px;display:flex;flex-direction:column;flex-shrink:0;height:100vh;}
.logo {font-size:22px;font-weight:700;color:#fff;padding:0 12px 32px 12px;display:flex;align-items:center;gap:10px;}
.nav-item {padding:10px 16px;border-radius:10px;color:#94a3b8;display:flex;align-items:center;gap:14px;text-decoration:none;font-size:14px;font-weight:500;transition:0.2s;margin-bottom:4px;}
.nav-item:hover {background:#1e293b;color:#f1f5f9;}
.nav-item.active {background:#1e293b;color:#fff;}
.main {flex:1;padding:32px;overflow-y:auto;}
.card {background:#1e293b;border:1px solid #334155;border-radius:16px;padding:24px;margin-bottom:24px;}
.card h3 {font-size:18px;margin-bottom:16px;color:#f1f5f9;}
.form-row {display:flex;gap:12px;flex-wrap:wrap;align-items:center;}
.form-row input {padding:10px 16px;background:#0f172a;border:1px solid #334155;border-radius:12px;font-size:14px;color:#e2e8f0;flex:1;min-width:140px;}
.form-row input:focus {outline:none;border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,0.15);}
.btn {padding:8px 18px;border-radius:30px;font-size:13px;font-weight:600;border:none;cursor:pointer;transition:0.2s;}
.btn-primary {background:#3b82f6;color:#fff;}
.btn-primary:hover {background:#2563eb;}
.btn-success {background:#10b981;color:#fff;}
.btn-success:hover {background:#059669;}
.btn-danger {background:#ef4444;color:#fff;}
.btn-danger:hover {background:#dc2626;}
.user-item {padding:14px 0;border-bottom:1px solid #1e293b;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;}
.user-item form {display:inline-flex;gap:6px;align-items:center;flex-wrap:wrap;}
.msg {color:#10b981;margin-top:12px;font-size:14px;}
.blod_text {font-weight:blod;}

</style>
</head>
<body>
<aside class="sidebar">
  <div class="logo">  <span style="font-size:14px;background:#3b82f6;padding:2px 10px;border-radius:6px;">后台</span></div>
  <a href="/admin" class="nav-item active"><span>⚙️</span> 用户管理</a>
  <div style="flex:1;"></div>
  <a href="/logout" class="nav-item"><span>🚪</span> 退出登录</a>
</aside>
<main class="main">
  <h2 style="margin-bottom:24px;">⚙️ 用户管理</h2>
  <div class="card">
    <h3>新增用户</h3>
    <form class="form-row" method="post" action="/adduser">
      <input name="u" placeholder="用户名" required>
      <input name="p" placeholder="密码" required>
      <button class="btn btn-primary">添加</button>
    </form>
    {% if msg %}<div class="msg">{{ msg }}</div>{% endif %}
  </div>
  <div class="card">
    <h3>👥 现有用户</h3>
    {% for u,p in users.items() %}
    <div class="user-item">
      <span><strong>{{ u }}</strong> <span style="color:#64748b;font-size:13px;margin-left:12px;">密码: {{ p }}</span></span>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <form action="/change_password" method="post" style="display:inline-flex;gap:4px;align-items:center;">
          <input type="hidden" name="user" value="{{ u }}">
          <input type="password" name="new_password" placeholder="新密码" required style="padding:6px 12px;background:#0f172a;border:1px solid #334155;border-radius:8px;font-size:13px;color:#e2e8f0;width:130px;">
          <button type="submit" class="btn btn-success">修改</button>
        </form>
        {% if u != 'admin' %}
        <form action="/deluser" method="post" onsubmit="return confirm('确定删除用户 {{ u }} <span class="blod_text">及其所有文件</span>吗？');">
          <input type="hidden" name="u" value="{{ u }}">
          <button type="submit" class="btn btn-danger">删除</button>
        </form>
        {% endif %}
      </div>
    </div>
    {% endfor %}
  </div>
</main>
</body>
</html>
"""

@flask_app.route("/adduser", methods=["POST"])
def adduser():
    if session.get("user") != "admin":
        return redirect("/")
    u = request.form.get("u","").strip()
    p = request.form.get("p","").strip()
    if u and p:
        if u in config["users"]:
            msg = f"用户 {u} 已存在"
        else:
            config["users"][u] = p
            save_config(config)
            os.makedirs(get_user_root(u), exist_ok=True)
            msg = f"用户 {u} 添加成功"
    else:
        msg = "用户名或密码不能为空"
    return redirect("/admin?msg=" + msg)

@flask_app.route("/deluser", methods=["POST"])
def deluser():
    if session.get("user") != "admin":
        return redirect("/")
    u = request.form.get("u","")
    if u in config["users"] and u != "admin":
        del config["users"][u]
        save_config(config)
        user_dir = get_user_root(u)
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir, ignore_errors=True)
        msg = f"用户 {u} 已删除"
    else:
        msg = "无法删除该用户"
    return redirect("/admin?msg=" + msg)

@flask_app.route("/change_password", methods=["POST"])
def change_password():
    if session.get("user") != "admin":
        return redirect("/")
    u = request.form.get("user","").strip()
    new_pwd = request.form.get("new_password","").strip()
    if u in config["users"] and new_pwd:
        config["users"][u] = new_pwd
        save_config(config)
        msg = f"用户 {u} 密码已更新"
    else:
        msg = "修改失败，请检查用户名或密码"
    return redirect("/admin?msg=" + msg)

@flask_app.route("/change_password_self", methods=["POST"])
def change_password_self():
    if "user" not in session:
        return redirect("/login")
    user = session["user"]
    if user == "admin":
        return redirect("/admin")

    old_pwd = request.form.get("old_password", "").strip()
    new_pwd = request.form.get("new_password", "").strip()
    confirm_pwd = request.form.get("confirm_password", "").strip()

    if not old_pwd or not new_pwd or not confirm_pwd:
        return redirect("/?msg=所有字段均为必填")
    if new_pwd != confirm_pwd:
        return redirect("/?msg=两次输入的新密码不一致")
    if user not in config["users"]:
        return redirect("/?msg=用户不存在")
    if config["users"][user] != old_pwd:
        return redirect("/?msg=旧密码错误")

    config["users"][user] = new_pwd
    save_config(config)
    write_log("change_password", user, status="success", detail="用户自行修改密码")
    return redirect("/?msg=密码修改成功！")


def create_dual_stack_socket(port):
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.bind(('::', port))
    sock.listen(5)
    return sock

def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8",80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def run_flask():
    port = config["port"]
    sock = create_dual_stack_socket(port)

    print('=' * 50)
    print('===== 服务器已启动 =====')
    print(f'本地局域网访问: http://{get_ip()}:{port}')
    print(f'用户根目录: {config["share_path"]}')
    print(f'日志文件: {config["log_file"]}')

    if config.get("announcement_url"):
        print(f'公告来源: {config["announcement_url"]}')
    print('=' * 50)

    print('默认管理员账号: admin 密码：123456')
    serve(flask_app, sockets=[sock], threads=8)

end = perf_counter()
print(f'资源加载完成，共耗时 {(end - start):.3f} 秒')
print('=' * 50)

if __name__ == "__main__":
    run_flask()
    input()
