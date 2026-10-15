# 久坐提醒 · Windows 版构建包

> 这是一个**独立文件夹**，和本机 macOS 版的「久坐提醒/」完全分开，互不影响。
> 这里收录的是 **Windows 专用** 的程序与打包配置，目标产物是一个
> **双击即用、目标电脑不需要安装 Python** 的 `久坐提醒.exe`。

---

## 目录内容

| 文件 | 作用 |
|------|------|
| `sit_reminder_windows.pyw` | Windows 版源码（常驻桌面小人 + 任务面板） |
| `app_icon.ico` | 程序图标（蓝底举拳小人，含 16~256 多分辨率） |
| `file_version_info.txt` | exe 的版本信息（右键属性里显示的那些字段） |
| `久坐提醒.spec` | PyInstaller 打包规格（单文件 / 无控制台窗口） |
| `build_exe.bat` | Windows 上一键打包脚本（需本机有 Python） |
| `requirements_build.txt` | 打包用的依赖（pyinstaller） |
| `久坐提醒.iss` | Inno Setup 安装包脚本（可选，生成真正的 setup.exe） |
| `.github/workflows/build-windows.yml` | GitHub Actions 自动构建工作流（无需本机环境） |

---

## 怎么拿到 `久坐提醒.exe`？

PyInstaller **不能**在 macOS 上交叉编译 Windows 的 exe，所以本机（macOS）
无法直接产出 exe。请用下面任一方式，在 **Windows** 上生成：

### 方式 A：在本机有 Python 的 Windows 电脑上打包（最简单）

1. 把整个「久坐提醒_Windows版」文件夹拷到 Windows 电脑。
2. 双击运行 `build_exe.bat`。
3. 等待完成后，在 `dist\久坐提醒.exe` 拿到成品。

> 过程中会临时安装 `pyinstaller`（仅打包用，不影响最终 exe）。
> 把 `dist\久坐提醒.exe` 拷到任意 Windows 电脑双击即可运行，
> **目标电脑无需安装 Python**。

### 方式 B：用 GitHub Actions 自动出包（完全不需要本机有 Python/Windows）

1. 把本文件夹作为仓库推送到 GitHub（或把它放进你已有的仓库）。
2. 在仓库的 **Actions** 标签里找到 `Build Windows EXE`，点 **Run workflow**。
3. 跑完后到 **Artifacts** 下载 `久坐提醒-exe`，里面就是 `久坐提醒.exe`。
4. （可选）给代码打一个 `v1.0.0` 之类的 tag 并推送，Actions 会自动把
   exe 发布到 **Releases**，可直接下载。

---

## 想做成「安装程序」（setup.exe）？

PyInstaller 产出的 `久坐提醒.exe` 本身已经是免安装的单文件程序。
如果你想要一个带「下一步/下一步」、能建开始菜单和桌面快捷方式、
还能勾选「开机自启」的正规安装包：

1. 先按上面方式 A/B 生成 `dist\久坐提醒.exe`。
2. 安装免费工具 [Inno Setup](https://jrsoftware.org/isdl.php)。
3. 用 Inno Setup 打开 `久坐提醒.iss` 并编译，得到 `installer\久坐提醒安装包.exe`。

---

## 运行说明

- 首次运行会弹欢迎语；数据保存在 `C:\Users\<你>\AppData\Roaming\久坐提醒\`
  （任务 `tasks.json`、设置 `settings.json`、运行日志 `运行日志.txt`）。
- 屏幕右缘常驻半透明小人；鼠标停在小人上约 0.6 秒拉出面板；
  双击面板顶栏 / 点右上角 ✕ / 按 Esc 收起；右键小人或面板可退出。
- 单实例运行：重复启动会自动切换到已运行的实例。

---

## 与本机 macOS 版的关系

- macOS 版在 `../久坐提醒/`（含 `.app`），**未经本包改动**。
- 本文件夹是纯 Windows 构建产物来源，二者互不干扰。
- 若以后要同步功能改动，请分别改两份源码，再重新走上面的打包流程。
