# 边狱补译 · Limbus AI Bridge

个人用《Limbus Company》临时补译工具，版本 **1.0.7**。用于填补游戏更新与都市零协会汉化更新之间的空窗，支持用户自己的 Chat Completions 兼容 API。

## 功能

- 对照本机游戏原文与零协会语言包，识别缺少译文的字段；首次扫描建立基线，后续新增或变更内容才默认列入“更新待补译”。
- 覆盖人格、主动/被动技能、背景剧情、E.G.O、敌人、主线及卡池等文本。
- 网络失败和校验失败自动重试，每条最多重试 10 次；支持 1–4 批并行及成功结果缓存。
- 跨界面译名一致性：统一状态与弹窗、技能等级、正文引用及剧情名称。先确定被正文引用的新名称，再继续并行翻译。
- 保留 Hana、Zwei 等协会数字专名；校验数字、引擎标记、变量、富文本和换行。
- 创建独立的 LimbusAI_zh-CN 语言包；原游戏文本、LLC 工具箱、零协会原文件和游戏语言配置只读。
- 更新本工具自己的语言包前备份；检测到额外或人工修改的文件时停止覆盖。

一致性检查与格式校验不能代替语义审校。普通对白差异、同词异义和无法证明的对应关系不会强行合并；可识别的疑似冲突进入“译名需核对”。

## 使用

1. 完成游戏更新，并通过原 LLC 工具箱安装或更新零协会汉化。
2. 退出游戏，打开边狱补译。
3. 在“API 设置”填写地址、API Key 和模型；支持标准 /chat/completions 兼容接口。
4. 扫描并勾选需要的内容，点击“翻译勾选项”。只有这一步会请求所配置的 API。
5. 审阅后生成独立语言包，在游戏自定义语言中选择 **LimbusAI_zh-CN**，按游戏提示重启。

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
    .\.venv\Scripts\python.exe -m PyInstaller --onefile --windowed --name LimbusAIBridge-1.0.7 --distpath release --workpath build-v107 main.py

可执行程序独立启动自检：

    .\release\LimbusAIBridge-1.0.7.exe --self-test --data-dir .\research\self-test

1.0.7 已通过 149 项离线测试，涵盖扫描、重试预算、并行、取消、文件保护和术语一致性。测试使用临时夹具，不调用真实翻译 API。

## 数据与隐私

仓库仅包含工具源码、测试、文档和构建配置。个人设置、密钥、译文缓存、日志、本机验收资料、游戏文本、零协会译文、字体和生成包均不进入 Git。

工具从本机读取游戏与语言包。翻译时只发送用户所选条目及相关上下文、参考语种与术语给所配置的服务商。后台同步只合并本地语言包，不自动调用付费 API。

## 资料与许可

- [Project Moon 自定义语言说明](https://steamcommunity.com/games/1973530/announcements/detail/533220039674824264)
- [都市零协会文档](https://www.zeroasso.top/docs/install/install/)
- [LocalizeLimbusCompany](https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany)

本项目非 Project Moon 或都市零协会官方产品。工具源码采用 [MIT License](LICENSE)。游戏数据、零协会译文和字体保留各自许可；MIT 不覆盖这些资源。合并语言包会保留本地原有署名与许可。
