# 快速问答助手 (quiz-ai-helper)

轻量级 Windows 桌面答题工具:**本地 OCR 实时识别屏幕内容 → 自动发送给小米 MiMo 大模型 → 流式显示答案**。识别快、回答快、零额外依赖。

## 功能特性

- 🖱️ **截图识别 (F2)**:拖拽框选屏幕任意区域,双击确认 / Esc 或右键取消
- 📁 **打开图片 / 识别剪贴板**:支持 PNG / JPG / BMP / WEBP / TIFF
- ⚡ **本地 OCR**:调用 Windows 原生 OCR(winocr),中文优先,识别即回显,零上传延迟
- 🤖 **流式回答**:MiMo 大模型逐字流式返回,实时显示响应速度
- 🧠 **全系模型**:mimo-v2.5 / mimo-v2.5-pro / mimo-v2.5-pro-ultraspeed 下拉切换
- 🧹 **一键清空**:清空文本框,同时中断 MiMo 服务端生成(断连即停,不浪费 Token)
- ⚙️ **灵活配置**:Base URL 下拉(按量付费 / Token Plan)、模型下拉、系统提示词自定义
- 📶 **测试连通**:一键验证 Key + 网络,显示「连通成功,响应X.XX秒」
- 🎁 **邀请福利**:内置"免费领取10体验金"入口,悬停可查看宣传图

## 快速开始

### 环境要求

- Windows 10 及以上版本
- Python 3.10+（开发环境为 3.14）
- Windows 自带 OCR 组件（Win10 默认已包含）

### 安装

```bash
pip install -r requirements.txt
```

### 运行

```bash
python app.py
```

### 首次使用

1. 点击工具栏 **设置**
2. **用你自己的 MiMo API Key**(在 https://platform.xiaomimimo.com 注册获取)
   - `sk-` 开头 → Base URL 选 `https://api.xiaomimimo.com/v1`(按量付费)
   - `tp-` 开头 → Base URL 选 `https://token-plan-cn.xiaomimimo.com/v1`(Token Plan)
3. 点「测试连通」确认网络与 Key 正常,保存
4. 按 **F2** 框选题目区域,稍等即自动识别并发送,答案流式出现

> ⚠️ **安全提醒**:API Key 属于你个人,请勿将 `config.json` 分享给任何人。

## 配置说明

程序会在运行目录自动生成/读取 `config.json`(被 .gitignore 忽略,不会提交):

```json
{
  "api_key": "",
  "base_url": "https://api.xiaomimimo.com/v1",
  "model": "mimo-v2.5",
  "temperature": 0.2,
  "max_tokens": 2048,
  "system_prompt": "直接简洁回答用户问题,不要分析过程,优先给出答案",
  "auto_send": true
}
```

常用配置项均可直接在「设置」界面修改,无需手工编辑文件。

## 项目结构

```
app.py            主程序(界面 + 逻辑)
mimo_client.py    MiMo API 客户端(流式 / 中断)
ocr_engine.py     Windows OCR 封装
screenshot.py     屏幕选区截图
requirements.txt  依赖清单
config.example.json  配置模板
```

## 邀请福利 🎁

新用户通过以下链接注册小米 MiMo 开放平台,**双方各得 ¥10 API 体验金**(40天有效):

```
https://platform.xiaomimimo.com?ref=99SDJQ
```

软件内「设置 → 免费领取10体验金」按钮已内置该入口。

## 免责声明

本项目仅供学习交流,请遵守小米 MiMo 平台服务协议与相关法律法规。