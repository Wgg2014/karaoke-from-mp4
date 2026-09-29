# Karaoke From MP4 + SRT

一个面向 Windows 11 的本地 Codex Skill：使用已经人工核对好的 MP4 和 SRT，生成三行滚动卡拉OK字幕、烧录版视频和带透明通道的字幕覆盖轨。

本 Skill 不进行语音识别，不翻译歌词，不转换简繁体，也不会修改输入视频和 SRT。过长的单条 SRT 会在合适的语义边界拆成每段最多八个字符的连续字幕段，文字不会丢失。

## 功能

- 三行滚动歌词：上一行、当前行、下一行。
- 当前歌词通过 ASS `\kf` 标签从左向右逐字变为玫红色。
- 白色粗体、黑色描边和轻微阴影，适合竖屏视频。
- 先生成10秒预览并验证，再生成完整视频。
- 输出 H.264/AAC 烧录版 MP4。
- 输出带真实 Alpha 通道的 ProRes 4444 透明字幕 MOV。
- 硬件编码不可用时自动回退到 `libx264`。
- 支持中文、空格和特殊字符路径。

## 运行环境

- Windows 11
- Python 3.12
- FFmpeg 和 FFprobe，且 FFmpeg 必须包含 libass 的 `subtitles`/`ass` 滤镜
- Codex 桌面端或其他支持本地 Skill 的 Codex 环境

### 安装依赖

安装 Python：

```powershell
winget install --id Python.Python.3.12 -e
```

安装 Git（使用 Git 下载方式时需要）：

```powershell
winget install --id Git.Git -e
```

安装 FFmpeg：

```powershell
winget install Gyan.FFmpeg
```

安装后重新打开 PowerShell，然后检查：

```powershell
python --version
ffmpeg -version
ffprobe -version
ffmpeg -hide_banner -filters | findstr /I "subtitles ass"
```

如果最后一条命令找不到 `subtitles` 或 `ass`，请改用包含 libass 的 Gyan full build。

## 下载与安装 Skill

### 方法一：使用 Git 克隆

在 PowerShell 中运行：

```powershell
git clone https://github.com/Wgg2014/karaoke-from-mp4.git "$env:USERPROFILE\.codex\skills\karaoke-from-mp4"
```

安装后应能直接找到：

```text
C:\Users\你的用户名\.codex\skills\karaoke-from-mp4\SKILL.md
```

如果目标目录已经存在，请先将原目录改名备份，再执行克隆；不要直接覆盖其中的个人修改。

### 方法二：下载 ZIP

1. 打开本仓库页面。
2. 点击 `Code` → `Download ZIP`。
3. 解压后将文件夹重命名为 `karaoke-from-mp4`。
4. 将整个文件夹放到：

   ```text
   C:\Users\你的用户名\.codex\skills\karaoke-from-mp4
   ```

5. 确认 `SKILL.md` 直接位于上述目录内，而不是多嵌套了一层文件夹。
6. 重新打开 Codex，或开始一个新会话以刷新 Skill 列表。

## 使用方法

准备两个文件：

- 一个 `.mp4` 视频；
- 一个人工核对过歌词和时间轴的 `.srt` 字幕。

在 Codex 中输入，例如：

```text
使用 $karaoke-from-mp4 处理 D:\视频\歌曲.mp4 和 D:\视频\歌曲.srt
```

Skill 会自动检查环境、复制项目模板、保留输入 SRT 原文、生成10秒预览、验证透明通道并完成全部输出。如果同名输出目录已经存在，会自动建立带时间戳的新目录，不覆盖旧结果。

### 直接使用命令行

也可以跳过 Codex 对话，直接运行：

```powershell
python "$env:USERPROFILE\.codex\skills\karaoke-from-mp4\scripts\run_karaoke.py" `
  "D:\视频\歌曲.mp4" `
  "D:\视频\歌曲.srt"
```

可选参数：

```text
--output-dir <目录>   指定任务输出目录
--title <歌名>        添加固定标题，默认关闭
--font-size-scale <倍率> 调整稳定默认字号；0.9/1.0/1.1/1.2 分别表示 -10%/默认/+10%/+20%
--preview-only        只生成 ASS 和两个10秒预览
--ass-only            只验证 SRT 并生成 ASS
```

首次运行会在 `%LOCALAPPDATA%\karaoke-from-mp4\runtime` 建立独立 Python 环境并安装 PyYAML，不会修改系统 Python 配置。

## 输出文件

默认在 MP4 旁边生成 `<视频名>_卡拉OK输出` 目录：

```text
<视频名>_卡拉OK输出/
├─ input/
│  └─ 歌曲.srt
└─ output/
   ├─ 三行卡拉OK字幕.ass
   ├─ 歌词预览_10秒.mp4
   ├─ 透明卡拉OK字幕_10秒预览.mov
   ├─ 最终视频_已烧录字幕.mp4
   ├─ 透明卡拉OK字幕.mov
   └─ 处理日志.log
```

其中：

- `最终视频_已烧录字幕.mp4`：H.264 + AAC，可直接发布。
- `透明卡拉OK字幕.mov`：ProRes 4444、无音频，用作剪映上方覆盖轨。
- `三行卡拉OK字幕.ass`：渲染中间文件。
- `input/*.srt`：输入 SRT 的字节级副本，用于核对，不会改写原文件。

## 剪映使用步骤

1. 将原始 MP4 放到主轨道。
2. 将 `透明卡拉OK字幕.mov` 放到上方轨道。
3. 两个素材从 `00:00` 完全对齐。
4. 不要对字幕 MOV 单独变速、裁切或改变帧率。
5. 最后由剪映统一导出。

透明 MOV 会保持原视频的分辨率、帧率、时长和帧数。4K 竖屏的 ProRes 4444 文件可能很大，这是正常现象。

## 默认字幕样式

- Microsoft YaHei UI 粗体；
- 1080×1920 基准画布使用 PlayRes 1080×1920、Fontsize 84、字号倍率 1.0；
- 当前行白色底字，逐字变为 `#FF4057`；
- 上下行白色半透明；
- 黑色粗描边和轻微阴影；
- 三行位于画面中下部；
- 切换动画约0.20秒；
- 水平居中，每个滚动字幕段最多八个字符，长句按语义拆成连续时间段；
- 标题、频谱和粒子默认关闭。

稳定默认配置只有一个来源：`assets/project-template/config.yaml`。启动器复制该配置但不重写它；如只需临时调整字号，优先使用 `--font-size-scale`。

## 更新

使用 Git 安装时：

```powershell
git -C "$env:USERPROFILE\.codex\skills\karaoke-from-mp4" pull
```

如果使用 ZIP 安装，请重新下载 ZIP，并先备份自己修改过的配置后再替换旧版本。

## 常见问题

### 提示 FFmpeg 缺少 libass

当前 FFmpeg 不含 `subtitles`/`ass` 滤镜。安装 Gyan full build，并重新打开终端。

### 硬件编码失败

程序会依次尝试 NVENC、QSV、AMF，均不可用时自动回退到 `libx264`。只要最终日志显示生成成功，就不影响使用。

### 透明 MOV 很大

ProRes 4444 需要保存高质量颜色和 Alpha 通道，尤其是2160×3840等4K竖屏视频，数百MB至数GB都可能是正常的。

### 歌词内容不正确

本 Skill 不识别或修改歌词。请先修正原 SRT，再使用修正后的 MP4 和 SRT 重新运行。

## 本地测试

```powershell
cd assets\project-template
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

当前字幕解析、长句双段拆分和 ASS 生成测试均位于 `assets/project-template/tests/`。
