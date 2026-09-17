# 边狱补译 · Limbus AI Bridge

个人用《Limbus Company》临时补译工具，版本 **1.2.4**。用于填补游戏更新与都市零协会汉化更新之间的空窗，支持用户自己的 Chat Completions 兼容 API。

[下载 Windows 版](https://github.com/zayin3390-max/LimbusAIBridge/releases/latest)

## 功能

- 原文/译文双栏工作台；分页、分类和关键词搜索，失败项与译名待核对单独筛选。
- 勾选跨页和筛选保留；编辑草稿自动保存，关闭后可继续修改。
- 常用 API 设置与高级选项分开，运行记录按需展开。

- 对照本机游戏原文与零协会语言包，识别缺少译文的字段；首次扫描建立基线，后续新增或变更内容才默认列入“本次更新”。
- 覆盖人格、主动/被动技能、背景剧情、E.G.O、敌人、主线及卡池等文本。包含 RPGSystem 探索对话、选项、说话人、NPC、任务目标、道具属性和界面提示。
- 默认“待补译”合并新内容与探索资源缺漏；“缺漏补查”单独显示探索文本，避免被“本次更新为 0”掩盖。
- 已有 AI／手动译文可勾选后“重译所选”；调用前备份旧结果，失败或停止时保留未完成条目的旧译文，失败状态可在重启后继续查看。
- 网络失败和校验失败自动重试，每条最多重试 10 次；支持 1–4 批并行及成功结果缓存。
- 角色语料：从本地人工汉化配对检索同角色、同人格和相近句式，参考有出处的称呼与常用表达；帮助页可导出逐角色对照文档。
- 扫描结果持久缓存：启动只读取缓存，不自动扫描或定时检查；更新后手动扫描。
- 小窗口适配：固定操作栏、按钮换行与滚动内容，重译／报告在紧凑布局中收纳到“更多操作”。
- 分语境词汇表：80 个核心术语、15 位主要角色语气与本地原译对照；按本地汉化提取良秀缩写范例，新释义进入“译名待核对”。[查看词汇表](docs/GLOSSARY.md)。
- 跨界面译名一致性：统一状态与弹窗、技能等级、正文引用及剧情名称。先确定被正文引用的新名称，再继续并行翻译。
- 保留 Hana、Zwei 等协会数字专名；校验数字、引擎标记、变量、富文本和换行。
- 创建独立的 LimbusAI_zh-CN 语言包；原游戏文本、LLC 工具箱、零协会原文件和游戏语言配置只读。
- 更新本工具自己的语言包前备份；检测到额外或人工修改的文件时停止覆盖。

一致性检查与格式校验不能代替语义审校。普通对白差异、同词异义和无法证明的对应关系不会强行合并；可识别的疑似冲突进入“译名待核对”。

## 使用

1. 完成游戏更新，并通过原 LLC 工具箱安装或更新零协会汉化。
2. 退出游戏，打开边狱补译。
3. 在“API 设置”填写地址、API Key 和模型；支持标准 /chat/completions 兼容接口。
4. 扫描并勾选需要的内容，点击“翻译所选”。翻译和连接测试会请求所配置的 API。
5. 审阅后生成语言包，在游戏自定义语言中选择 **LimbusAI_zh-CN**，按游戏提示重启。

升级时先关闭旧工具窗口。新旧 EXE 放在同一目录可继续使用旁边 data 目录中的设置与缓存。

详细说明见 [使用指南](docs/USER_GUIDE.md)，版本记录见 [CHANGELOG](CHANGELOG.md)。

## 从源码运行与构建

开发基准为 Windows 和 Python 3.12。程序运行使用 Python 标准库及 Tkinter；Windows DPAPI 用于可选的密钥加密保存。

运行：

    python main.py

运行离线测试：

    python -m unittest discover -s tests -v

构建 Windows EXE：

    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
    .\.venv\Scripts\python.exe -m PyInstaller --onefile --windowed --name LimbusAIBridge-1.2.4 --distpath release --workpath build-v124 main.py

可执行程序独立启动自检：

    .\release\LimbusAIBridge-1.2.4.exe --self-test --data-dir .\research\self-test

1.2.4 已通过 279 项离线测试，涵盖扫描、重试预算、并行、取消、文件保护、术语一致性、界面交互、草稿恢复与探索资源支持。测试使用临时夹具，不调用真实翻译 API。

## 数据与隐私

仓库仅包含工具源码、测试、文档和构建配置。个人设置、密钥、译文缓存、日志、本机验收资料、游戏文本、零协会译文、字体和生成包均不进入 Git。

工具从本机读取游戏与语言包。翻译时只发送用户所选条目及相关上下文、参考语种、术语及检索到的少量人工原译对照给所配置的服务商。启动和定时任务不会扫描或调用付费 API；翻译、扫描和生成包均由用户发起。

## 资料与许可

- [Project Moon 自定义语言说明](https://steamcommunity.com/games/1973530/announcements/detail/533220039674824264)
- [都市零协会文档](https://www.zeroasso.top/docs/install/install/)
- [LocalizeLimbusCompany](https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany)

本项目非 Project Moon 或都市零协会官方产品。工具源码采用 [MIT License](LICENSE)。游戏数据、零协会译文和字体保留各自许可；MIT 不覆盖这些资源。合并语言包会保留本地原有署名与许可。
