# 极简版小助手 — 常见问题 FAQ

---

## 一、安装 Python

### Q: 我需要安装什么？
只需要安装 **Python 3.9 或更高版本**，其他依赖会自动安装。

下载地址：https://www.python.org/downloads/

### Q: Windows 安装 Python 时要注意什么？
安装时 **一定要勾选「Add Python to PATH」**（在安装界面最下方的复选框）。如果忘了勾选，需要卸载重装。

### Q: Mac 怎么安装 Python？
两种方式：
1. 直接去 python.org 下载安装包
2. 如果装了 Homebrew，终端输入：`brew install python`

### Q: 怎么确认 Python 装好了？
打开终端（Mac）或命令提示符（Windows），输入：

```
python --version
```

或者（Mac）：

```
python3 --version
```

看到类似 `Python 3.11.5` 就说明装好了。

---

## 二、启动应用

### Q: Windows 找不到启动文件？
解压后进入 `studio/` 文件夹，双击 **`启动工作站.bat`**（不是 `.command`，那个是 Mac 用的）。

### Q: Mac 双击 `.command` 文件提示「无法打开」或「来自未知开发者」？
右键点击 `启动工作站.command` → 选择「打开」→ 弹窗中再点「打开」。只需要第一次这样操作。

如果还不行，打开终端执行：

```
chmod +x studio/启动工作站.command
```

然后再双击。

### Q: 提示「未找到 python3」或「python 不是内部命令」？
说明 Python 没有加到系统 PATH 中。

**Windows 解决办法：**
1. 重新运行 Python 安装程序
2. 选择「Modify」
3. 确保勾选「Add Python to PATH」

**Mac 解决办法：**
打开终端输入 `which python3`，如果没有输出，重新从 python.org 安装。

### Q: 安装依赖时报错 `pip` 相关错误？
尝试手动安装。打开终端/命令提示符，进入解压后的根目录，运行：

**Windows：**
```
python -m pip install -r requirements.txt
```

**Mac：**
```
python3 -m pip install -r requirements.txt
```

### Q: 提示端口 8501 已被占用？
说明上次的应用没有完全关闭。

**Windows：** 打开任务管理器，找到 `python` 进程，结束它，再重新启动。

**Mac：** 终端输入：
```
lsof -ti:8501 | xargs kill -9
```

然后再双击启动。

---

## 三、配置 API Key

### Q: 在哪里获取 API Key？
根据你想用的模型服务商：

| 服务商 | 获取地址 |
|--------|----------|
| DeepSeek | https://platform.deepseek.com/api_keys |
| Google Gemini | https://aistudio.google.com/apikey |
| OpenAI (GPT) | https://platform.openai.com/api-keys |
| 通义千问 | https://dashscope.console.aliyun.com/ |
| 月之暗面 (Kimi) | https://platform.moonshot.cn/console/api-keys |
| 豆包 (Doubao) | https://console.volcengine.com/ark |

### Q: 三个模型插槽（主力/创意/长文本）必须填不同的吗？
**不用。** 三个都填同一个就行，「快速配置」功能就是帮你一键填相同的。

### Q: 保存 API Key 后提示错误？
1. 确认 Key 没有多余的空格
2. 确认 Key 格式正确（一般以 `sk-` 开头）
3. 关闭应用重新启动再试

### Q: 提示 API 调用失败？
可能原因：
- API Key 过期或余额不足
- 网络问题（部分服务商需要科学上网）
- 模型名称填错

---

## 四、使用问题

### Q: 页面一直转圈/没有反应？
AI 生成需要时间，特别是「灵感模式」（脑暴有多轮讨论）和「调研模式」（多轮搜索）。请耐心等待 1-3 分钟。

### Q: 可以在手机上用吗？
可以。在电脑上启动应用后，启动界面会显示一个 Network URL（类似 `http://192.168.x.x:8501`）。手机连同一个 WiFi，浏览器打开这个地址即可。

### Q: 怎么关闭应用？
直接关闭终端/命令行窗口即可。

### Q: 数据保存在哪里？
- API Key 保存在根目录的 `.env` 文件中
- 决策日志保存在 `studio/decision_logs.json` 中
- 脑暴记录保存在 `runs/` 文件夹中

所有数据都在本地，不会上传到任何服务器。

---

## 五、快速排障

遇到问题时，按这个顺序检查：

1. **Python 装了吗？** → `python --version`
2. **依赖装了吗？** → `python -m pip install -r requirements.txt`
3. **API Key 配了吗？** → 打开应用主页检查状态
4. **重启试试？** → 关掉窗口，重新双击启动

如果以上都试过还有问题，把终端窗口里的错误信息截图发给我。
