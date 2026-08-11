# AGENTS.md

Windows-only tkinter 桌面答题工具(Python 3.10+,开发环境 3.14):本地 OCR → 小米 MiMo API 流式答题。界面文案全部为中文。无测试框架、无 lint。

## 运行与验证

- 运行:`python app.py`(PowerShell:`cd "C:\Users\Ghost\Documents\Default Project"; python app.py`)
- 无单元测试;验证方式:`python -m py_compile app.py history_store.py`,再用 `python -c "import app; a=app.App(); ..."` 做 UI 冒烟测试
- 控制台打印中文会乱码(GBK 代码页),断言/对比前先 `$env:PYTHONIOENCODING='utf-8'`;乱码不影响程序内部(文件均 UTF-8)
- 弹窗类(messagebox/grab_set)会阻塞 mainloop,测试脚本里需用 `root.after(...)` 调度后再 destroy

## 推送规矩(用户明确要求,违反会挨骂)

- **只有用户明确说"推送"才 commit/push**;平时改动只本地提交
- **每次推送前必须先去敏**:`config.json`、`history.json` 已在 .gitignore,但提交前要确认无 API Key 泄漏(扫 `sk-`/`tp-` 前缀、检查 `api_key` 只有参数引用);key 只存在于本地 config.json
- **每次推送必须同步修改 README.md** 反映本次改动
- **每次推送都要给用户一份发行版说明**(markdown 可直接粘贴 GitHub 新建发行版);只列「新增/优化」,**不要加「使用说明」章节**(用户明确要求)
- 发布版本:改 `app.py` 的 `APP_VERSION` → commit → `git tag vX.Y.Z` → `git push origin main --tags`;tag 是钉死的快照,旧 Release 不随新代码更新

## 架构要点

- `app.py`:全部 UI + 逻辑(入口);后台线程与主线程通过 `queue.Queue` + `_handle_event` 分发事件(`_push("event", ...)`)
- `mimo_client.py`:MiMo API 客户端,`stream_chat(text, stop_event)` 逐行流式;`StreamStopped` 异常 = 被中断(先 `response.close()` 停服务端)
- `ocr_engine.py`(winocr 封装)、`screenshot.py`(RegionSelector 框选 + grab_region)
- `history_store.py`:history.json 读写,`add_record` 同题去重、上限 500
- 流式并发安全:每个请求带 `_req_id`,`stream_start/token/done/stopped/error` 事件都按 req_id 过滤,防历史事件串台
- 区域自动识别(`_region_monitor`):300ms 采样缩略图差值,连续满足「内容识别延迟(秒)」(`config["region_stable"]`,默认 0.6)才触发;触发条件在 `region_changed` 事件,生成中触发会置 `_pending_region_change` 在 stream_done 后补发
- 全自动答题:用户分别框选「正确」/「错误」选项的屏幕区域(`option_correct`/`option_wrong`),MiMo 返回答案后匹配关键词(正确/对/是 → 正确区域,错误/错/否 → 错误区域),用 `ctypes.mouse_event` 模拟点击;自动答题开启时系统提示词追加「如果是判断题,只回答正确或错误」;历史记录新增 `sel` 字段

## 配置与格式

- `config.json` 本地自动生成;字段:`api_key/base_url/model/temperature/max_tokens/system_prompt/auto_send/auto_region/region_stable/auto_answer/option_correct/option_wrong/geometry/update_repo`;`config.example.json` 是模板,api_key 必须留空
- 设置弹窗字段名与 config key 一一对应,新增设置项要同步改 `DEFAULT_CONFIG`、设置弹窗 rows、`_save` 校验
- 按钮风格:设置/历史库按钮统一 `width=8`,布局用 grid + weight=1 两侧列居中,勿用 pack fill/expand(会拉伸/压扁)
