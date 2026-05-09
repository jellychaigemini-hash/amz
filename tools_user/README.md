# Rufus 自动模式 · Chrome 启动工具

## start_chrome_for_rufus.bat

双击即可开启带 CDP 调试端口的 Chrome，复用你平时登录 Amazon 的真实 profile。

### 为什么需要这个

Rufus 面板只在**登录状态 + 真实浏览器指纹**下才会稳定加载。如果我们自己
从零 launch 一个干净 profile 的 Chrome，Amazon 会因为：
- Cookie 空白
- Geo / 指纹异常
- 新 IP 首次访问

把 Rufus 功能限流 / 不加载 / 弹 CAPTCHA。用你真实用过的 profile 绕开这些问题。

### 使用步骤

1. **完全关闭所有 Chrome 窗口**（包括后台的）
2. 双击 `start_chrome_for_rufus.bat`
3. Chrome 打开后你会看到 Amazon 首页，左下角出现 Rufus 浮窗表示可用
4. 回到本应用点「测试 Chrome 连通」→ 应显示 available
5. 点「开始自动调研」，程序会接管这个浏览器跑 10 题

### 手动启动（如果 bat 不合适）

```cmd
taskkill /F /IM chrome.exe /T
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --remote-allow-origins=* ^
  --profile-directory=Default ^
  https://www.amazon.com/
```

### 常见问题

- **端口 9222 已被占用**：可能之前的调试 Chrome 还在，`taskkill /F /IM chrome.exe` 清干净
- **bat 找不到 Chrome**：在 bat 里把路径改成你的安装目录
- **想用非 Default 的 profile**：改 bat 里的 `PROFILE_DIR=Default` 为 `Profile 1` 等

### 安全说明

- 这个脚本不会向任何外部网络发送数据
- 调试端口仅监听 `127.0.0.1:9222`，不对外暴露
- 程序只发送 Runtime.evaluate 做问题注入，不读取其他 tab
