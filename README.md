# 快速问答助手 (quiz-ai-helper)

> 当前版本 v0.3.5

轻量级 Windows 桌面答题工具:**本地 OCR 实时识别屏幕内容 → 自动发送给小米 MiMo 大模型 → 流式显示答案**。识别快、回答快、零额外依赖。

## 功能特性

- 🖱️ **截图识别 (F2)**:拖拽框选屏幕任意区域,双击确认 / Esc 或右键取消
- 📁 **打开图片 / 识别剪贴板**:支持 PNG / JPG / BMP / WEBP / TIFF
- ⚡ **本地 OCR**:调用 Windows 原生 OCR(winocr),中文优先,识别即回显,零上传延迟
- 🤖 **流式回答**:MiMo 大模型逐字流式返回,实时显示响应速度;渲染链路优化(30 倍)+ 队列轮询 30ms,长答案显示更流畅
- 🧠 **全系模型**:mimo-v2.5 / mimo-v2.5-pro / mimo-v2.5-pro-ultraspeed 下拉切换
- 🧹 **一键清空**:清空文本框,同时中断 MiMo 服务端生成(断连即停,不浪费 Token)
- 📚 **历史库**:自动记录查询过的题目与答案(同题去重、上限 500 条),每条显示 序号 + 题目 / 答案,点击载入并高亮,点击其他位置取消选中
- 🪟 **左右分栏**:左侧 识别结果/答案,右侧 历史库,分隔条可拖动
- ✏️ **答案可编辑**:答案区与识别结果区均可直接修改(支持撤销),可手动修正模型输出
- 🔭 **区域自动识别**:勾选后框选一次题目区域,框内内容发生变化(新题出现)即自动识别并发送,无需反复框选;识别延迟可在设置中调整
- 🎯 **自动答题**:用可拖动/缩放的半透明定位框标出各选项位置(默认「正确」「错误」支持判断题),点绿色 ➕ 可继续添加选项框(默认 A、B、C…),双击框可直接改文字;支持单选/多选,答案匹配到多个框时依次自动点击(间隔 0.15 秒)
- ⚙️ **灵活配置**:Base URL 下拉(按量付费 / Token Plan)、模型下拉、系统提示词自定义
- 📶 **测试连通**:一键验证 Key + 网络,显示「连通成功,响应X.XX秒」
- 🔄 **检查更新**:位于设置弹窗内,对比 GitHub 最新 Release 版本;发现新版本可「不再提醒」忽略指定版本
- 🎁 **邀请福利**:内置「领取￥10」入口,悬停可查看宣传图

## 快速开始

直接下载最新版:https://github.com/GhostCmdr/quiz-ai-helper/releases/latest
双击 quiz-ai-helper.exe 即可使用(Windows 10+,无需安装 Python)

源码运行:pip install -r requirements.txt && python app.py

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
  "system_prompt": "直接回答用户的问题,不要分析过程,不要输出思考过程,不要给出答案解析,直接给出答案",
  "auto_send": true,
  "auto_region": false,
  "region_stable": 0.6,
  "auto_answer": false,
  "option_zones": [],
  "update_repo": "GhostCmdr/quiz-ai-helper",
  "update_silent": ""
}
```

常用配置项均可直接在「设置」界面修改,无需手工编辑文件。`history.json` 为历史库数据(同样被 .gitignore 忽略,不会提交)。

> 💡 **区域自动识别**:勾选「区域自动识别」后按 F2 框选题目区域,之后框内内容一旦变化(如刷新出新题)并稳定超过「内容识别延迟(默认 0.6 秒,可在设置调整)」,即自动识别并按「识别后自动发送」勾选状态发送。建议框选纯题目区域,避免答案区域内容变化引起重复触发。

## 项目结构

```
app.py            主程序(界面 + 逻辑)
mimo_client.py    MiMo API 客户端(流式 / 中断)
ocr_engine.py     Windows OCR 封装
screenshot.py     屏幕选区截图
history_store.py  历史库读写(去重 / 上限)
requirements.txt  依赖清单
config.example.json  配置模板
```

## 邀请福利 🎁

新用户通过以下链接注册小米 MiMo 开放平台,**双方各得 ¥10 API 体验金**(40天有效):

```
https://platform.xiaomimimo.com?ref=99SDJQ
```

软件内「设置 → 领取￥10」按钮已内置该入口。

## 免责声明

本项目仅供学习交流,请遵守小米 MiMo 平台服务协议与相关法律法规。