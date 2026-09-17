from __future__ import annotations
import json
import os
import pathlib
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog
from . import VERSION
from . import settings
from .core import (BridgeError, Cancelled, Cache, scan_game, signature, install_pack,
                   export_report, game_running, detect_game, PACK_NAME, MARKER, PACK_RULES_VERSION, atomic_write)
from .provider import Client, translate, include_dependencies
from .consistency import align_translations
from .retranslation import retranslate,eligible as retranslation_eligible
from .ui_model import DraftStore, MODES, FIELD_LABELS, matches, selected, preview

CATEGORIES=('人格','E.G.O','主线剧情','敌方','卡池','关联术语','其他')
REASONS={'missing':'缺失','empty':'空值待确认','placeholder':'待译标记','foreign':'韩文待核对','mixed':'混合语言待核对','same':'原文保留待核对','metadata':'剧情附加字段'}
STATES={'pending':'待译','cached':'已有译文','ignored':'已忽略','failed':'校验/请求失败'}
HELP='''使用顺序

1. 先让 Steam 和游戏完成本次更新，再退出游戏。
2. 用原来的 LLC 工具箱更新零协会汉化（若已有更新）。
3. 打开本工具，在「API 设置」填写自己的 Chat Completions 兼容地址、API Key、模型名。
4. 「扫描更新」后选择分类。默认勾选新增待译内容，以及 RPGSystem 探索场景中缺少译文的条目。探索对话、任务、NPC、道具和界面文本归入「主线剧情」。
5. 点击「翻译所选」。这一步才会发送所选游戏文本到你配置的 API，并消耗服务商额度。
6. 检查译文后点击「生成语言包」。此操作不调用 API。
7. 在游戏启动页的自定义语言按钮中选择 LimbusAI_zh-CN，按游戏提示重启。基础语言推荐英文。

零协会更新后

本工具以本地 LLC_zh-CN 为基准。窗口保持打开时，每 60 秒检查一次本地文件；有变化且游戏已退出时自动重建独立包。新到的零协会译文优先，原有 AI 缓存保留备用。没有自动付费翻译，也不会自动下载零协会更新。
关闭软件后不监控；下次打开会同步。若从原工具箱启动游戏，它可能把选定语言切回 LLC_zh-CN，此时在游戏启动页重新选择 LimbusAI_zh-CN。

如何识别新内容

按 ID、探索资源 key、技能等级和硬币位置对齐；同一资源组中，总表已经汉化的相同 ID、相同原文不会再次报缺。首次扫描建立当前原文基线，不把存量差异称为新版本漏译。「本次更新」只显示基线之后新增/变更且缺少译文的字段。默认「待补译」还包含已支持的探索资源缺漏，可在「缺漏补查」单独查看；即使本次更新为 0，也可能有这类缺漏。首次使用时若更新已经发生，或要核对旧文本，可手动切到「所有条目」查看。
原文保留、空值、剧情省略字段、旧文件等只表示文件差异，不证明当前游戏画面缺译。하나协会等专名保留；中文夹杂外语也不作为自动重译依据。明确开发备注和有译文覆盖的重复导出文件会排除，依据写入扫描报告。无法安全对齐的重复 ID 保留原状。

协会数字专名

Hana、Zwei、Tres、Shi、Cinq、Liu、Devyat'、Dieci、Öufi 等按原文拼写保留；纯专名不会列为待译，整句翻译时也会保护其拼写。Seven/Eight 在明确的协会语境或单独名称中保留，普通数量照常翻译。Association/Assoc.、方位、科室与职务照常汉化。零协会已有的一协、二协等译文继续保留。

文件保护

官方入口：LimbusCompany_Data/Lang/自定义语言名。原版游戏文件、LLC_zh-CN、LLC 工具箱和原 config.json 均只读取。本工具只创建/维护自己的 LimbusAI_zh-CN 目录；若遇到同名非本工具目录，或你手动修改了生成包，立即停止覆盖。每次变更保留上一份受影响文件于 data/history；不用的自有旧文件移到 data/retired。回到原汉化只需在游戏里选 LLC_zh-CN。

翻译范围与质量

人格：名字、主动/被动技能、背景剧情和语音文本。E.G.O：名称、觉醒/侵蚀技能、被动及语音。敌方：名字、技能、被动与观察记录。另含主线文本与卡池说明。本工具只处理官方导出的文本 JSON，不识别图片里的文字，不改图像或游戏逻辑。
引擎关键词、富文本、变量、换行及数字会校验；不通过的条目不会进入生成包。校验只能保证部分格式和数字，不能保证语义正确，尤其应核对技能条件。AI 会参考本机的韩文/日文和零协会已有术语。

词汇表与角色语气

内置 80 个核心术语及 15 位主要角色的语气规则。战斗 Coin 使用“硬币”，Golden Bough 使用“金枝”；饰品、章节货币和普通词义分开处理。孤立饰品名不会直接成为其他文件中普通词语的译法。当前说话人由对白字段或专属语音文件判断，不靠一句话提到了谁来猜测。
角色译例从本地人工汉化按字段配对读取；优先同人格、同场景，再参考相近句式，每条最多附 3 组原译。称呼、语气词和常见句式均附使用条件与出处，缺少对应语料时不凭印象设定口癖。
良秀的缩写会从本地零协会汉化中读取对应范例，并附上当前前后台词。只有同一完整原句的已知缩写直接锁定；新场景中的缩写需结合韩日参考，进入“译名待核对”。单独一个尚无释义的缩写先留待人工确认，不反复消耗 API 请求。角色语气服从当段情绪、人格及剧情阶段，不强加口癖。
扫描和生成包时会修正现有 AI 缓存中能明确识别的术语错译；原始缓存、手动审校和零协会原包保留。其它可疑译法仅提示核对，不能保证全部语义正确。
在“帮助”点击“导出词表与语料”，或使用“导出报告”，可获得词表 Markdown、CSV、角色语料 Markdown／JSON 和本地良秀缩写候选。无扫描时只导出内置规则；扫描后附上本地对白及出处。数据目录中的 glossary.json 可指定个人译法，重扫后应用。完整词表见同包“边狱巴士词汇表.md”。

自动重试

网络中断、超时、限流和服务器临时故障会自动等待后重试，默认最多 10 次（不含首次请求）。等待逐步增加，通常不超过 60 秒；服务返回更长等待时间时遵照其提示。日志显示重试进度，可随时点击“停止”取消等待。
达到上限后，当前批次标为失败，继续处理后面的批次；不会把失败批次拆开以绕过重试上限。已成功条目立即保存，下次重试不会重复发送。密钥失效、额度/付款错误或接口设置错误需要人工修正，会提示并结束本轮。保护标记、数字、中文正文和 JSON 格式校验失败也会自动纠正重试；只重发失败条目，成功项先保存。网络失败与校验失败共用每条最多 10 次重试额度，不会各重试 10 次。长输出/批次格式失败会缩小批次，拆分前已用次数仍然保留。失败原因会写入 validation-failures.jsonl 供核对，不保存密钥和被拒绝的完整响应。
可在 API 设置修改重试次数（0–10），0 表示关闭自动重试。

跨界面译名一致

扫描、翻译结束、生成语言包时统一检查：状态栏与弹窗，技能各等级，技能/被动正文引用，人格、E.G.O、敌人名称，剧情说话人、称谓和地点，章节及卡池中的术语。相同资源按实体 ID、字段和原文对应；跨 ID 的名称还需本地韩文/日文等对应证据，不把不同实体仅凭同英文强行合并。
零协会已有译名优先；缺失处再使用个人术语、手动审校和已有 AI 定名。已知名称会在 API 请求中锁定。若本次勾选了尚未翻译、且会被正文引用的名称，先翻译名称，再按原有并行数处理正文；不会擅自发送未勾选条目。
普通对白、同词异义、不同数值与硬币描述分别保留；Hana、Zwei 等协会数字专名的规则不变。正文中已识别的别译在原文确实提及对应术语时修正。无法确定的新别译列入「译名待核对」，可查看原文、参考语种并手动审校；导出报告会附上「译名一致性.md」及「译名对齐清单.csv」。
原汉化不改写，原始缓存记录保留；在内存和生成的独立包中统一。完整人工名称优先于较短名称片段。此功能检查可识别的术语关系，不代替全文语义审校。
升级后，退出游戏、关闭旧工具窗口，重新打开新版并点击「生成语言包」即可应用现有译文修复，无需重新付费翻译。开启自动同步时，新版也会在游戏退出后按新规则同步。


加速翻译

API 设置新增「并行批次」：默认 2，可设 1–4。2 表示同时处理两批；接口允许时可改为 4，设为 1 恢复逐批模式。已有成功译文继续复用；不同批次各自处理，某批纠错时其他批次可继续。
校验纠错仅等待 1 秒；断网、超时及服务器故障仍使用原来的逐步退避，最多 10 次重试的共同上限不变。并行请求收到限流或服务端等待指示时，会暂停所有通道的新请求。已发出的请求可能仍在返回，停止后会保留其中通过校验的译文，再结束本轮。
保持每批 12–20 条通常便于控制输出长度；频繁出现“输出达到长度上限”时可调小到 6–10。并行数越高不保证越快，具体取决于服务商限额、模型速度和重试情况。没有更换模型或关闭质量校验。

API 与隐私

支持标准 /chat/completions 接口（包含 OpenAI 兼容的中转、DeepSeek、部分本地服务）。不直接支持 /responses、Anthropic /messages 或 Gemini 原生接口；这些服务需使用兼容网关。模型名可以手填或获取列表。JSON 模式默认关闭，减少服务商兼容性问题。
密钥默认只保留在当前进程；勾选「加密记住」后用当前 Windows 用户的 DPAPI 加密保存。不会在日志、报告或请求错误里写出密钥。选定条目的原文、附近对白、参考语种、相关零协会术语及检索出的少量人工对白译例会发给你填写的服务商。不会读取其它软件的 API Key。
可在 data/glossary.json 填写 {"原文术语":"中文译名"} 来补充个人术语。

资料来源

Project Moon 官方自定义翻译说明（2025-03-31）：
https://steamcommunity.com/games/1973530/announcements/detail/533220039674824264
官方分离 Title/Context 字体说明（1.74.0）：
https://store.steampowered.com/news/app/1973530/view/533221941907030183
零协会文档：
https://www.zeroasso.top/docs/install/install/
https://www.zeroasso.top/docs/devNotes/
https://www.zeroasso.top/docs/install/hotupdate/
https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany

这是个人补译工具，不是 Project Moon 或都市零协会出品。已有汉化及其许可证会随本地合并包保留，零协会文本使用 CC BY-NC-SA 4.0；请保留署名，勿将含其文本的包用于商业分发。
'''


BG='#F3F5F7'
PAPER='#FFFFFF'
INK='#202B35'
MUTED='#6B7885'
LINE='#DFE5EA'
ACCENT='#237965'
NAV='#202D37'
DANGER='#B44343'

HELP_PAGES={
'快速开始':"""1  扫描
更新游戏和零协会汉化，选择游戏目录并扫描。

2  翻译
勾选需要的条目，填写 API 后点击“翻译所选”。

3  应用
退出游戏，生成语言包。在游戏里选择 LimbusAI_zh-CN，按提示重启。

升级工具
关闭旧窗口，将新版放在原目录，继续使用旁边的 data 文件夹。""",
'常见问题':"""扫描后没有待翻译内容？
“待补译”包含新增内容及已支持的探索场景缺漏。“本次更新”只显示基线之后的变化；“缺漏补查”可单独查看探索文本。其他旧差异在“所有条目”查看。

翻译失败怎么办？
临时错误和校验失败会自动重试，最多 10 次。达到上限后处理后续条目；修正设置后可在“失败项”中重新勾选。

如何重译已有内容？
扫描后切到“已有译文”或“译名待核对”，勾选条目，再点击“重译所选”。更多菜单可选中全部筛选结果。重译会调用 API 并消耗额度；旧译文先备份，失败时保留。完成后生成语言包。

为什么名称会不同？
软件会对齐可确认的名称及引用。疑似冲突列入“译名待核对”；语义仍需人工审阅。

零协会更新后怎么办？
开启自动同步时，工具会在游戏退出后重新合并。新汉化优先，AI 缓存保留。

切换条目前要保存吗？
编辑草稿会保留；点击“保存译文”并通过校验后，才会用于语言包。""",
'文件与隐私':"""API
支持 Chat Completions 兼容接口。连接测试和翻译会发送文本到所配置的服务商，测试消耗少量额度。

密钥
“记住密钥”使用当前 Windows 用户加密保存，密钥不写入日志。

文件
原游戏文本、零协会文件和语言配置只读。工具只维护 LimbusAI_zh-CN，更新前备份；发现人工改动时停止覆盖。

数据
设置、缓存、编辑草稿和备份保存在程序旁的 data 文件夹。

关于
Limbus AI Bridge · 个人补译工具
非 Project Moon 或都市零协会官方产品。
源码采用 MIT；游戏文本、汉化与字体保留各自许可。"""
}

class App:
    def __init__(self,root,directory,*,autostart=True):
        self.root=root;self.directory=pathlib.Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True)
        self.cache=Cache(self.directory)
        self.config,self.api_key=settings.load(self.directory)
        self.drafts=DraftStore(self.directory)
        self.scan=None;self.checked=set();self.visible={};self.current=None
        self.filtered=[];self.page_index=0;self.page_size=200
        self.events=queue.Queue();self.stop=threading.Event();self.busy=False;self.worker=None
        self.closing=False;self.watch_pending=False;self.last_watch_signature=''
        self.controls=[];self.editables=[];self.job_entries=[];self.operation=''
        self._loading=False;self._editor_original='';self._search_after=None;self._draft_after=None
        self._last_progress_update=0
        self.page='work';self.log_open=False;self.advanced_open=False
        root.title(f'边狱补译 · {VERSION}')
        width=min(1380,root.winfo_screenwidth()-60);height=min(880,root.winfo_screenheight()-80)
        root.geometry(f'{width}x{height}')
        root.minsize(min(1040,width),min(660,height));root.configure(bg=BG)
        self.configure_styles();self.build_shell()
        self.build_work(self.pages['work'])
        self.build_settings(self.pages['settings']);self.build_help(self.pages['help'])
        self.show_page('work')
        root.protocol('WM_DELETE_WINDOW',self.on_close)
        root.bind('<Control-f>',self.focus_search);root.bind('<Control-s>',self.shortcut_save)
        root.bind('<F5>',lambda event:self.start_scan())
        root.after(100,self.poll)
        self.refresh()
        if self.drafts.error:self.write_log(self.drafts.error)
        if autostart:
            root.after(450,self.start_scan);root.after(60000,self.watch)

    def configure_styles(self):
        style=ttk.Style(self.root);style.theme_use('clam')
        style.configure('.',font=('Microsoft YaHei UI',10),background=BG,foreground=INK)
        style.configure('TFrame',background=BG);style.configure('Paper.TFrame',background=PAPER)
        style.configure('TLabel',background=BG,foreground=INK)
        style.configure('Paper.TLabel',background=PAPER);style.configure('Muted.TLabel',foreground=MUTED)
        style.configure('Title.TLabel',font=('Microsoft YaHei UI',19,'bold'))
        style.configure('TButton',padding=(13,8),background=PAPER,borderwidth=1,relief='flat')
        style.map('TButton',background=[('active','#EAF0F2'),('disabled','#EEF1F3')],foreground=[('disabled','#98A1AA')])
        style.configure('Primary.TButton',background=ACCENT,foreground='white',borderwidth=0,padding=(18,10))
        style.map('Primary.TButton',background=[('active','#1A6253'),('disabled','#E1E7E8')],
                  foreground=[('disabled','#909C9F'),('!disabled','white')])
        style.configure('Small.TButton',padding=(9,5))
        style.configure('TEntry',fieldbackground=PAPER,bordercolor=LINE,lightcolor=LINE,darkcolor=LINE,padding=8)
        style.configure('TCombobox',fieldbackground=PAPER,background=PAPER,bordercolor=LINE,padding=7,arrowsize=14)
        style.map('TCombobox',fieldbackground=[('readonly',PAPER)])
        style.configure('TSpinbox',fieldbackground=PAPER,padding=7,bordercolor=LINE,arrowsize=14)
        style.configure('TCheckbutton',background=BG,padding=3)
        style.configure('Paper.TCheckbutton',background=PAPER)
        style.configure('Treeview',rowheight=38,font=('Microsoft YaHei UI',10),fieldbackground=PAPER,
                        background=PAPER,foreground=INK,borderwidth=0)
        style.configure('Treeview.Heading',font=('Microsoft YaHei UI',9,'bold'),background='#EDF1F4',
                        foreground=MUTED,padding=(8,9),relief='flat')
        style.map('Treeview',background=[('selected','#DEEEE8')],foreground=[('selected','#185847')])
        style.configure('Horizontal.TProgressbar',background=ACCENT,troughcolor='#E1E7EA',borderwidth=0,thickness=4)
        style.configure('TNotebook',background=BG,borderwidth=0)
        style.configure('TNotebook.Tab',padding=(16,9))
        style.map('TNotebook.Tab',background=[('selected',PAPER)],foreground=[('selected',ACCENT)])
        style.configure('TPanedwindow',background=LINE)

    def build_shell(self):
        sidebar=tk.Frame(self.root,bg=NAV,width=170);sidebar.pack(side='left',fill='y');sidebar.pack_propagate(False)
        tk.Label(sidebar,text='边狱补译',font=('Microsoft YaHei UI',18,'bold'),fg='#F7FAFC',bg=NAV).pack(anchor='w',padx=22,pady=(28,2))
        tk.Label(sidebar,text='Limbus AI Bridge',font=('Segoe UI',9),fg='#94A8B5',bg=NAV).pack(anchor='w',padx=23,pady=(0,30))
        self.nav_buttons={}
        for key,label in [('work','翻译工作台'),('settings','API 设置'),('help','帮助')]:
            button=tk.Button(sidebar,text=label,anchor='w',font=('Microsoft YaHei UI',11),padx=18,pady=12,
                             bg=NAV,fg='#C3CFD8',activebackground='#31424D',activeforeground='white',
                             relief='flat',borderwidth=0,cursor='hand2',command=lambda key=key:self.show_page(key))
            button.pack(fill='x',padx=10,pady=3);self.nav_buttons[key]=button
        tk.Label(sidebar,text='v'+VERSION,font=('Segoe UI',9),fg='#94A8B5',bg=NAV).pack(side='bottom',anchor='w',padx=24,pady=20)
        self.log_toggle=tk.Button(sidebar,text='运行记录',anchor='w',font=('Microsoft YaHei UI',10),padx=16,pady=10,
                                  bg=NAV,fg='#B5C4CE',activebackground='#31424D',activeforeground='white',
                                  relief='flat',borderwidth=0,command=self.toggle_log)
        self.log_toggle.pack(side='bottom',fill='x',padx=10,pady=5)
        main=ttk.Frame(self.root);main.pack(side='left',fill='both',expand=True)
        self.status=tk.StringVar(value='就绪')
        footer=ttk.Frame(main,padding=(24,8,24,12));footer.pack(side='bottom',fill='x')
        status_row=ttk.Frame(footer);status_row.pack(fill='x')
        self.status_label=ttk.Label(status_row,textvariable=self.status,style='Muted.TLabel')
        self.status_label.pack(side='left',fill='x',expand=True)
        status_row.bind('<Configure>',lambda e:self.status_label.configure(wraplength=max(300,e.width-110)))
        self.stop_button=ttk.Button(status_row,text='停止',style='Small.TButton',command=self.request_stop,state='disabled')
        self.stop_button.pack(side='right',padx=(10,0))
        self.progress=ttk.Progressbar(footer,mode='determinate',maximum=100);self.progress.pack(fill='x',pady=(8,0))
        self.log_frame=ttk.Frame(main,padding=(24,0,24,8))
        self.log=tk.Text(self.log_frame,height=6,wrap='word',font=('Microsoft YaHei UI',9),relief='flat',
                         padx=12,pady=9,bg='#E9EEF1',fg='#52616E',state='disabled')
        scrollbar=ttk.Scrollbar(self.log_frame,command=self.log.yview);self.log.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right',fill='y');self.log.pack(fill='both',expand=True)
        self.page_host=ttk.Frame(main);self.page_host.pack(fill='both',expand=True)
        self.pages={key:ttk.Frame(self.page_host,padding=(24,22,24,4)) for key in ('work','settings','help')}

    def show_page(self,key):
        for name,frame in self.pages.items():
            frame.pack_forget()
            self.nav_buttons[name].configure(bg='#354954' if name==key else NAV,fg='white' if name==key else '#C3CFD8')
        self.pages[key].pack(fill='both',expand=True);self.page=key
        if hasattr(self,'key_entry'):
            self.key_entry.configure(show='●');self.key_button.configure(text='显示')
        if hasattr(self,'translate_button'):self.root.after_idle(self.update_actions)

    def button(self,parent,text,command,primary=False,*,small=False):
        widget=ttk.Button(parent,text=text,command=command,
                         style='Primary.TButton' if primary else 'Small.TButton' if small else 'TButton')
        widget.pack(side='left',padx=(0,8));self.controls.append(widget);return widget

    def build_work(self,frame):
        head=ttk.Frame(frame);head.pack(fill='x')
        ttk.Label(head,text='翻译工作台',style='Title.TLabel').pack(side='left')
        self.scan_button=ttk.Button(head,text='扫描更新',command=self.start_scan)
        self.scan_button.pack(side='right');self.controls.append(self.scan_button)
        self.game_var=tk.StringVar(value=self.config['game_path'])
        path_row=ttk.Frame(frame);path_row.pack(fill='x',pady=(14,16))
        ttk.Label(path_row,text='游戏目录',style='Muted.TLabel').pack(side='left',padx=(0,10))
        self.game_entry=ttk.Entry(path_row,textvariable=self.game_var)
        self.game_entry.pack(side='left',fill='x',expand=True,padx=(0,8));self.editables.append((self.game_entry,'normal'))
        self.button(path_row,'选择',self.choose_game,small=True)
        stats=ttk.Frame(frame);stats.pack(fill='x',pady=(0,14));self.stat_values={}
        for key,label,mode in [('pending','待翻译','待补译'),('cached','已有译文','已有译文'),('failed','失败','失败项'),('review','译名待核对','译名待核对')]:
            card=tk.Frame(stats,bg=PAPER,highlightthickness=1,highlightbackground=LINE)
            card.pack(side='left',fill='x',expand=True,padx=(0,8))
            value=tk.StringVar(value='—');self.stat_values[key]=value
            line=tk.Frame(card,bg=PAPER);line.pack(fill='x',padx=15,pady=10)
            number=tk.Label(line,textvariable=value,font=('Segoe UI',20,'bold'),bg=PAPER,fg=DANGER if key=='failed' else INK)
            number.pack(side='left')
            text=tk.Label(line,text=label,font=('Microsoft YaHei UI',9),fg=MUTED,bg=PAPER);text.pack(side='left',padx=(12,0))
            for w in (card,line,number,text):
                w.configure(cursor='hand2');w.bind('<Button-1>',lambda event,mode=mode:self.choose_mode(mode))
        filters=ttk.Frame(frame);filters.pack(fill='x',pady=(0,10))
        self.mode=tk.StringVar(value='待补译')
        combo=ttk.Combobox(filters,textvariable=self.mode,values=MODES,state='readonly',width=15)
        combo.pack(side='left');combo.bind('<<ComboboxSelected>>',self.filter_changed)
        self.category=tk.StringVar(value='常用分类')
        self.category_vars={name:tk.BooleanVar(value=name!='其他') for name in CATEGORIES}
        combo=ttk.Combobox(filters,textvariable=self.category,values=('常用分类','所有分类')+CATEGORIES,state='readonly',width=12)
        combo.pack(side='left',padx=8);combo.bind('<<ComboboxSelected>>',self.category_changed)
        self.search=tk.StringVar()
        self.search_entry=ttk.Entry(filters,textvariable=self.search,width=22)
        self.search_entry.pack(side='right',fill='x',expand=True,padx=(10,0))
        ttk.Label(filters,text='搜索',style='Muted.TLabel').pack(side='right')
        self.search.trace_add('write',self.search_changed)
        self.search_entry.bind('<Escape>',lambda event:self.search.set(''))
        self.summary_var=tk.StringVar(value='')
        pane=ttk.Panedwindow(frame,orient='horizontal');pane.pack(fill='both',expand=True);self.work_pane=pane
        left=ttk.Frame(pane,style='Paper.TFrame');right=ttk.Frame(pane,style='Paper.TFrame',padding=14)
        pane.add(left,weight=6);pane.add(right,weight=5)
        pane.bind('<Configure>',self.initial_split)
        actions=ttk.Frame(left,style='Paper.TFrame',padding=(10,8));actions.pack(fill='x')
        self.select_button=self.button(actions,'全选本页',self.select_visible,small=True)
        self.clear_button=self.button(actions,'清空选择',self.clear_visible,small=True)
        self.more_button=ttk.Menubutton(actions,text='更多',style='Small.TButton')
        menu=tk.Menu(self.more_button,tearoff=False);menu.add_command(label='选中全部筛选结果',command=self.select_filtered)
        menu.add_separator();menu.add_command(label='忽略所选',command=self.ignore_checked);menu.add_command(label='恢复所选',command=self.unignore_checked)
        self.more_button.configure(menu=menu);self.more_button.pack(side='left');self.controls.append(self.more_button)
        self.list_host=ttk.Frame(left,style='Paper.TFrame');self.list_host.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(self.list_host,columns=('check','category','source','state'),show='headings',selectmode='browse')
        for key,text,width,stretch in [('check','选择',46,False),('category','分类',74,False),('source','原文',300,True),('state','状态',92,False)]:
            self.tree.heading(key,text=text);self.tree.column(key,width=width,minwidth=120 if stretch else width,stretch=stretch)
        for name,fg in [('failed',DANGER),('cached',ACCENT),('ignored','#9AA4AD'),('pending',INK)]:self.tree.tag_configure(name,foreground=fg)
        self.tree.tag_configure('alternate',background='#F7F9FA')
        scroll=ttk.Scrollbar(self.list_host,orient='vertical',command=self.tree.yview);self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.tree.pack(fill='both',expand=True)
        self.tree.bind('<Button-1>',self.on_tree_click);self.tree.bind('<<TreeviewSelect>>',self.show_entry)
        self.tree.bind('<space>',self.toggle_focused)
        self.tree.bind('<Control-a>',lambda event:(self.select_visible(),'break')[-1])
        self.empty=ttk.Frame(self.list_host,style='Paper.TFrame',padding=20)
        self.empty_title=tk.StringVar(value='先扫描游戏内容');self.empty_hint=tk.StringVar(value='选择游戏目录，然后点击“扫描更新”。')
        ttk.Label(self.empty,textvariable=self.empty_title,style='Paper.TLabel',font=('Microsoft YaHei UI',13,'bold')).pack(pady=(0,10))
        ttk.Label(self.empty,textvariable=self.empty_hint,style='Paper.TLabel',foreground=MUTED,wraplength=300,justify='center').pack()
        self.empty_action=ttk.Button(self.empty,text='查看所有条目',style='Small.TButton',command=lambda:self.choose_mode('所有条目'))
        self.empty_action.pack(pady=(14,0))
        pages=ttk.Frame(left,style='Paper.TFrame',padding=(10,7));pages.pack(fill='x')
        self.page_label=tk.StringVar();ttk.Label(pages,textvariable=self.page_label,style='Paper.TLabel',foreground=MUTED).pack(side='left')
        self.next_button=ttk.Button(pages,text='下一页',style='Small.TButton',command=lambda:self.change_page(1));self.next_button.pack(side='right')
        self.prev_button=ttk.Button(pages,text='上一页',style='Small.TButton',command=lambda:self.change_page(-1));self.prev_button.pack(side='right',padx=5)
        titles=ttk.Frame(right,style='Paper.TFrame');titles.pack(fill='x')
        self.detail_title=tk.StringVar(value='条目详情');self.dirty_var=tk.StringVar()
        ttk.Label(titles,textvariable=self.detail_title,style='Paper.TLabel',font=('Microsoft YaHei UI',12,'bold')).pack(side='left')
        ttk.Label(titles,textvariable=self.dirty_var,style='Paper.TLabel',foreground='#A06C23').pack(side='right')
        self.detail_var=tk.StringVar(value='选择左侧条目')
        self.detail_label=ttk.Label(right,textvariable=self.detail_var,style='Paper.TLabel',foreground=MUTED,wraplength=360)
        self.detail_label.pack(fill='x',pady=(5,10))
        right.bind('<Configure>',lambda event:self.detail_label.configure(wraplength=max(200,event.width-30)))
        row=ttk.Frame(right,style='Paper.TFrame');row.pack(fill='x',pady=(0,5))
        ttk.Label(row,text='原文',style='Paper.TLabel').pack(side='left')
        self.reference_button=ttk.Button(row,text='参考语种',style='Small.TButton',command=self.toggle_reference);self.reference_button.pack(side='right')
        self.showing_reference=False;self.original=self.text_box(right,8,readonly=True)
        row=ttk.Frame(right,style='Paper.TFrame');row.pack(fill='x',pady=(12,5))
        ttk.Label(row,text='译文',style='Paper.TLabel').pack(side='left')
        self.save_button=ttk.Button(row,text='保存译文',style='Small.TButton',command=self.save_manual,state='disabled');self.save_button.pack(side='right')
        self.revert_button=ttk.Button(row,text='还原',style='Small.TButton',command=self.revert_draft,state='disabled');self.revert_button.pack(side='right',padx=6)
        self.translation=self.text_box(right,8)
        self.translation.configure(undo=True,autoseparators=True,maxundo=80);self.translation.bind('<<Modified>>',self.editor_changed)
        actions=ttk.Frame(frame);actions.pack(fill='x',pady=(14,4))
        self.translate_button=self.button(actions,'翻译所选',self.start_translate,primary=True)
        self.retranslate_button=self.button(actions,'重译所选',self.start_retranslate)
        self.build_button=self.button(actions,'生成语言包',self.start_build)
        self.report_button=self.button(actions,'导出报告',self.report)
        self.selected_var=tk.StringVar(value='未选择条目');ttk.Label(frame,textvariable=self.selected_var,style='Muted.TLabel').pack(anchor='w',pady=(0,3))
        meta=ttk.Frame(frame);meta.pack(fill='x',pady=(4,0))
        ttk.Label(meta,textvariable=self.summary_var,style='Muted.TLabel').pack(side='left')
        self.monitor_var=tk.BooleanVar(value=self.config.get('monitor',True))
        self.sync_check=ttk.Checkbutton(meta,text='自动同步汉化更新',variable=self.monitor_var);self.sync_check.pack(side='right')

    def text_box(self,parent,height,readonly=False):
        holder=ttk.Frame(parent,style='Paper.TFrame');holder.pack(fill='both',expand=True)
        text=tk.Text(holder,height=height,width=34,wrap='word',font=('Microsoft YaHei UI',11),relief='flat',padx=11,pady=10,
                     background='#F7F9FA' if readonly else PAPER,foreground=INK,insertbackground=ACCENT,
                     selectbackground='#CDE9DF',highlightthickness=1,highlightbackground=LINE,highlightcolor=ACCENT)
        scroll=ttk.Scrollbar(holder,command=text.yview);text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');text.pack(fill='both',expand=True)
        if readonly:text.configure(state='disabled')
        return text

    def build_settings(self,frame):
        ttk.Label(frame,text='API 设置',style='Title.TLabel').pack(anchor='w',pady=(0,20))
        canvas=tk.Canvas(frame,bg=BG,highlightthickness=0)
        scroll=ttk.Scrollbar(frame,command=canvas.yview);scroll.pack(side='right',fill='y')
        canvas.pack(fill='both',expand=True);canvas.configure(yscrollcommand=scroll.set)
        form=ttk.Frame(canvas,padding=(22,20),style='Paper.TFrame')
        window=canvas.create_window((0,0),window=form,anchor='nw')
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(window,width=e.width))
        form.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        def wheel(event):
            canvas.yview_scroll(-int(event.delta/120),'units')
            return 'break'
        # Scope wheel scrolling to this page, including its children.
        self.settings_canvas=canvas
        form.columnconfigure(1,weight=1)
        self.api_vars={k:tk.StringVar(value=str(self.config.get(k,''))) for k in
                       ('api_base','model','baseline_path','timeout','batch_size','concurrency','max_tokens','retries')}
        def label(text,row,parent=form):
            ttk.Label(parent,text=text,style='Paper.TLabel').grid(row=row,column=0,sticky='w',padx=(0,22),pady=9)
        label('API 地址',0)
        address=ttk.Entry(form,textvariable=self.api_vars['api_base'])
        address.grid(row=0,column=1,columnspan=2,sticky='ew',pady=9);self.editables.append((address,'normal'))
        label('API Key',1)
        self.key_var=tk.StringVar(value=self.api_key)
        self.key_entry=ttk.Entry(form,textvariable=self.key_var,show='●')
        self.key_entry.grid(row=1,column=1,sticky='ew',pady=9);self.editables.append((self.key_entry,'normal'))
        self.key_button=ttk.Button(form,text='显示',style='Small.TButton',command=self.toggle_key)
        self.key_button.grid(row=1,column=2,padx=(8,0));self.controls.append(self.key_button)
        self.remember_var=tk.BooleanVar(value=self.config.get('remember_key',False))
        remember=ttk.Checkbutton(form,text='记住密钥（Windows 加密）',variable=self.remember_var,style='Paper.TCheckbutton')
        remember.grid(row=2,column=1,columnspan=2,sticky='w',pady=(0,12));self.editables.append((remember,'normal'))
        label('模型',3)
        self.model_combo=ttk.Combobox(form,textvariable=self.api_vars['model'])
        self.model_combo.grid(row=3,column=1,sticky='ew',pady=9);self.editables.append((self.model_combo,'normal'))
        fetch=ttk.Button(form,text='获取列表',style='Small.TButton',command=self.fetch_models)
        fetch.grid(row=3,column=2,padx=(8,0));self.controls.append(fetch)
        self.advanced_button=ttk.Button(form,text='▸ 高级设置',style='Small.TButton',command=self.toggle_advanced)
        self.advanced_button.grid(row=4,column=0,columnspan=3,sticky='w',pady=(22,10))
        self.advanced=ttk.Frame(form,style='Paper.TFrame');self.advanced.columnconfigure(1,weight=1)
        self.advanced.grid(row=5,column=0,columnspan=3,sticky='ew');self.advanced.grid_remove()
        numeric=[('concurrency','并行批次',1,4),('retries','最大重试次数',0,10),
                 ('batch_size','每批条目',1,40),('timeout','请求超时 / 秒',10,300),
                 ('max_tokens','输出长度上限',256,65536)]
        self.numeric_fields=numeric
        for row,(key,title,low,high) in enumerate(numeric):
            label(title,row,self.advanced)
            entry=ttk.Spinbox(self.advanced,textvariable=self.api_vars[key],from_=low,to=high,width=12)
            entry.grid(row=row,column=1,sticky='w',pady=7);self.editables.append((entry,'normal'))
            ttk.Label(self.advanced,text=f'{low}–{high}',style='Paper.TLabel',foreground=MUTED).grid(row=row,column=2,padx=12,sticky='w')
        label('零协会目录',5,self.advanced)
        base=ttk.Entry(self.advanced,textvariable=self.api_vars['baseline_path'])
        base.grid(row=5,column=1,columnspan=2,sticky='ew',pady=8);self.editables.append((base,'normal'))
        ttk.Label(self.advanced,text='留空自动识别',style='Paper.TLabel',foreground=MUTED).grid(row=6,column=1,sticky='w')
        self.json_var=tk.BooleanVar(value=self.config.get('json_mode',False))
        json_check=ttk.Checkbutton(self.advanced,text='JSON 输出模式',variable=self.json_var,style='Paper.TCheckbutton')
        json_check.grid(row=7,column=1,sticky='w',pady=12);self.editables.append((json_check,'normal'))
        buttons=ttk.Frame(form,style='Paper.TFrame');buttons.grid(row=6,column=0,columnspan=3,sticky='w',pady=(22,8))
        self.button(buttons,'保存设置',self.save_settings,primary=True)
        self.button(buttons,'测试连接',self.test_api)
        ttk.Label(form,text='连接测试会发送一条短请求，消耗少量 API 额度。',style='Paper.TLabel',foreground=MUTED).grid(row=7,column=0,columnspan=3,sticky='w',pady=8)
        self.api_status=tk.StringVar(value='')
        ttk.Label(form,textvariable=self.api_status,style='Paper.TLabel',foreground=ACCENT,wraplength=650).grid(row=8,column=0,columnspan=3,sticky='w',pady=8)
        def bind_wheel(widget):
            widget.bind('<MouseWheel>',wheel)
            for child in widget.winfo_children():bind_wheel(child)
        bind_wheel(form);canvas.bind('<MouseWheel>',wheel)

    def build_help(self,frame):
        ttk.Label(frame,text='帮助',style='Title.TLabel').pack(anchor='w',pady=(0,20))
        tabs=ttk.Notebook(frame);tabs.pack(fill='both',expand=True)
        for title,content in HELP_PAGES.items():
            page=ttk.Frame(tabs,padding=16,style='Paper.TFrame');tabs.add(page,text=title)
            box=self.text_box(page,20);box.insert('1.0',content);box.configure(state='disabled')
        row=ttk.Frame(frame);row.pack(fill='x',pady=(14,0))
        self.button(row,'打开数据目录',lambda:os.startfile(str(self.directory)))
        self.button(row,'导出词表与语料',self.export_glossary)

    def export_glossary(self):
        if self.busy:return
        from .language_knowledge import export_language
        def done(path):
            self.write_log('词汇表已导出：'+str(path))
            os.startfile(str(path))
        directory=self.directory/'reports'/('词汇表-'+time.strftime('%Y%m%d-%H%M%S'))
        self.run(lambda:export_language(self.scan,directory),done,'导出词表与语料')

    def toggle_log(self):
        self.log_open=not self.log_open
        if self.log_open:self.log_frame.pack(side='bottom',fill='x',before=self.page_host)
        else:self.log_frame.pack_forget()
        self.log_toggle.configure(text='收起记录' if self.log_open else '运行记录')

    def toggle_advanced(self):
        self.advanced_open=not self.advanced_open
        if self.advanced_open:self.advanced.grid()
        else:self.advanced.grid_remove()
        self.advanced_button.configure(text=('▾' if self.advanced_open else '▸')+' 高级设置')

    def toggle_key(self):
        visible=bool(self.key_entry.cget('show'))
        self.key_entry.configure(show='' if visible else '●')
        self.key_button.configure(text='隐藏' if visible else '显示')

    def focus_search(self,event=None):
        self.show_page('work');self.search_entry.focus_set();self.search_entry.selection_range(0,'end')
        return 'break'

    def shortcut_save(self,event=None):
        if not self.busy:
            if self.page=='settings':self.save_settings()
            elif self.page=='work':self.save_manual()
        return 'break'

    def initial_split(self,event):
        if event.width>600 and not getattr(self,'_split_initialized',False):
            self.work_pane.sashpos(0,int(event.width*.54));self._split_initialized=True

    def choose_mode(self,mode):
        self.mode.set(mode);self.search.set('');self.category.set('所有分类');self.category_changed()

    def category_changed(self,event=None):
        category=self.category.get()
        for name,var in self.category_vars.items():
            var.set(category=='所有分类' or (category=='常用分类' and name!='其他') or category==name)
        self.filter_changed()

    def filter_changed(self,event=None):
        self.page_index=0;self.refresh()

    def search_changed(self,*_):
        if self._search_after:self.root.after_cancel(self._search_after)
        self._search_after=self.root.after(220,self.filter_changed)

    def change_page(self,delta):
        self.page_index=max(0,min(self.page_index+delta,max(0,(len(self.filtered)-1)//self.page_size)))
        self.refresh()

    def collect_settings(self):
        config=dict(self.config);config.update({k:v.get().strip() for k,v in self.api_vars.items()})
        for key,title,low,high in self.numeric_fields:
            try:config[key]=int(config[key])
            except ValueError:raise BridgeError(f'{title}需要填写整数')
            if not low<=config[key]<=high:raise BridgeError(f'{title}应在 {low}–{high} 之间')
        config.update(game_path=self.game_var.get().strip(),remember_key=self.remember_var.get(),
                      json_mode=self.json_var.get(),monitor=self.monitor_var.get())
        return config,self.key_var.get().strip()

    def save_settings(self):
        if self.busy:return
        try:
            config,key=self.collect_settings();settings.save(self.directory,config,key)
            self.config=config;self.api_key=key;self.api_status.set('已保存');self.write_log('设置已保存')
        except Exception as exc:self.show_error(exc)

    def choose_game(self):
        path=filedialog.askdirectory(title='选择 Limbus Company 游戏目录',initialdir=self.game_var.get() or None)
        if path:self.game_var.set(path)

    def emit(self,text):self.events.put(('log',str(text)))

    def write_log(self,text,announce=True):
        text=str(text)
        for key in {self.api_key,self.key_var.get() if hasattr(self,'key_var') else ''}:
            if key:text=text.replace(key,'[密钥已隐藏]')
        if announce:
            self.status.set(text if len(text)<=110 else text[:109]+'…')
            self.status_label.configure(foreground=MUTED)
        line=f'[{time.strftime("%H:%M:%S")}] {text}\n'
        self.log.configure(state='normal');self.log.insert('end',line)
        lines=int(self.log.index('end-1c').split('.')[0])
        if lines>500:self.log.delete('1.0',f'{lines-500}.0')
        self.log.see('end');self.log.configure(state='disabled')
        try:
            with (self.directory/'activity.log').open('a',encoding='utf-8') as stream:stream.write(line)
        except OSError:pass

    def show_error(self,exc):
        text=str(exc)
        for key in {self.api_key,self.key_var.get()}:
            if key:text=text.replace(key,'[密钥已隐藏]')
        self.write_log(text);self.status_label.configure(foreground=DANGER);self.api_status.set(text)

    def request_stop(self):
        self.stop.set();self.stop_button.configure(state='disabled');self.write_log('正在停止，等待当前请求结束…')

    def run(self,fn,callback,operation='处理',entries=None):
        if self.busy:return
        self.remember_draft();self.busy=True;self.stop.clear();self.operation=operation;self.job_entries=entries or []
        self.update_actions();self.stop_button.configure(state='normal')
        self.progress.configure(mode='indeterminate');self.progress.start(12)
        self.write_log(f'正在{operation}…')
        def task():
            try:self.events.put(('done',(callback,fn())))
            except Cancelled as exc:self.events.put(('cancel',str(exc)))
            except Exception as exc:self.events.put(('error',exc))
        self.worker=threading.Thread(target=task,daemon=True);self.worker.start()

    def poll(self):
        try:
            while True:
                kind,data=self.events.get_nowait()
                if kind=='log':self.write_log(data);continue
                self.busy=False;self.progress.stop();self.progress.configure(mode='determinate',value=100 if kind=='done' else 0)
                self.stop_button.configure(state='disabled');self.update_actions()
                if kind=='done':
                    callback,result=data
                    try:callback(result)
                    except Exception as exc:self.show_error(exc)
                else:
                    self.refresh()
                    if kind=='error':self.show_error(data)
                    else:self.write_log(data)
                self.update_actions()
                if self.closing:self.flush_drafts();self.root.destroy();return
        except queue.Empty:pass
        if self.busy and self.job_entries and time.monotonic()-self._last_progress_update>.6:
            completed=sum(e.status in ('cached','failed') for e in self.job_entries)
            self.progress.stop();self.progress.configure(mode='determinate',value=100*completed/len(self.job_entries))
            self.selected_var.set(f'已处理 {completed} / {len(self.job_entries)} 条')
            self._last_progress_update=time.monotonic()
        self.root.after(100,self.poll)

    def start_scan(self):
        if self.busy:return
        game=self.game_var.get().strip();baseline=self.api_vars['baseline_path'].get().strip()
        if not game:self.write_log('请先选择游戏目录');return
        def work():
            scan=scan_game(game,baseline or None,self.config['source_lang'],self.cache,self.stop,self.emit)
            self.cache.observe(scan);return scan
        self.run(work,self.scanned,'扫描')

    def scanned(self,scan):
        self.remember_draft();self.current=None;self.scan=scan;self.last_watch_signature=scan.signature
        self.checked={e.uid for e in scan.entries if e.needs_translation and e.category!='其他'}
        self.page_index=0;self.refresh()
        gaps=sum(e.coverage_gap and e.status not in ('cached','ignored') for e in scan.entries)
        self.write_log(f'扫描完成 · 待翻译 {len(self.checked)} 条'+(f' · 探索缺漏 {gaps} 条' if gaps else ''))
        for message in scan.warnings:self.write_log(message,announce=False)
        changes=len({r['uid'] for r in scan.consistency_changes})
        if changes:self.write_log(f'已对齐 {changes} 个译名字段，生成语言包后生效',announce=False)
        marker=scan.game/'LimbusCompany_Data/Lang'/PACK_NAME/MARKER
        if self.monitor_var.get() and marker.exists():
            try:
                metadata=json.loads(marker.read_text(encoding='utf-8'))
                if metadata.get('source_signature')!=scan.signature or metadata.get('pack_rules_version',0)!=PACK_RULES_VERSION:
                    self.watch_pending=True;self.root.after(250,self.sync_pending)
            except (ValueError,OSError):pass

    def matches(self,entry):
        return matches(entry,self.mode.get(),{c for c,v in self.category_vars.items() if v.get()},self.search.get())

    def refresh(self):
        self.remember_draft()
        current_uid=self.current.uid if self.current else None
        self.filtered=[e for e in self.scan.entries if self.matches(e)] if self.scan else []
        self.page_index=min(self.page_index,max(0,(len(self.filtered)-1)//self.page_size))
        start=self.page_index*self.page_size
        children=self.tree.get_children()
        if children:self.tree.delete(*children)
        self.visible={}
        states={'pending':'待翻译','cached':'已保存','ignored':'已忽略','failed':'失败'}
        for i,e in enumerate(self.filtered[start:start+self.page_size]):
            iid=str(start+i);self.visible[iid]=e
            self.tree.insert('','end',iid=iid,values=('✓' if e.uid in self.checked else '',e.category,preview(e),('重译失败' if e.retranslation_error else states.get(e.status,e.status))),
                             tags=('failed' if e.retranslation_error else e.status,'alternate' if i%2 else ''))
        total=len(self.filtered);pages=max(1,(total+self.page_size-1)//self.page_size)
        self.page_label.set(f'{total:,} 条 · {self.page_index+1} / {pages} 页')
        self.prev_button.configure(state='normal' if self.page_index else 'disabled')
        self.next_button.configure(state='normal' if self.page_index+1<pages else 'disabled')
        if self.visible:self.empty.place_forget()
        else:
            if not self.scan:
                title,hint='先扫描游戏内容','选择游戏目录，然后点击“扫描更新”。'
            elif self.search.get().strip():
                title,hint='没有匹配的条目','试试其他关键词，或清空搜索。'
            elif self.mode.get() in ('本次更新','待补译','缺漏补查'):
                title,hint='当前筛选下没有待译内容','其他存量差异可在“所有条目”查看。'
            else:
                title,hint='这里还没有条目','切换分类或筛选条件后再查看。'
            self.empty_title.set(title);self.empty_hint.set(hint)
            if self.scan and self.mode.get()!='所有条目':self.empty_action.pack(pady=(14,0))
            else:self.empty_action.pack_forget()
            self.empty.place(relx=.5,rely=.5,anchor='center')
        entries=self.scan.entries if self.scan else []
        for key,number in [('pending',sum(e.needs_translation for e in entries)),
                           ('cached',sum(e.status=='cached' for e in entries)),
                           ('failed',sum(e.status=='failed' or bool(e.retranslation_error) for e in entries)),
                           ('review',sum(bool(e.consistency_note) for e in entries))]:
            self.stat_values[key].set(f'{number:,}' if self.scan else '—')
        self.summary_var.set(f'零协会 {self.scan.version}' if self.scan else '')
        keep=next((iid for iid,e in self.visible.items() if e.uid==current_uid),None)
        if keep is not None:self.tree.selection_set(keep);self.show_entry()
        else:self.clear_detail()
        self.update_selection_count()

    def selected_entries(self):
        if not self.scan:return []
        rows=selected(self.scan.entries,self.checked)
        return [e for e in include_dependencies(rows,self.scan) if e.status not in ('cached','ignored')] if rows else []

    def selected_retranslations(self):
        return [e for e in self.scan.entries if e.uid in self.checked and retranslation_eligible(e)] if self.scan else []

    def update_selection_count(self):
        rows=self.selected_entries()
        old=self.selected_retranslations()
        hidden=sum(e.uid in self.checked and (e.status not in ('cached','ignored') or retranslation_eligible(e)) for e in (self.scan.entries if self.scan else [])
                   if not self.matches(e))
        self.selected_var.set(f'待译 {len(rows)} 条 · 重译 {len(old)} 条'+(f' · 筛选外 {hidden} 条' if hidden else '') if rows or old else '未选择条目')
        self.retranslate_button.configure(text=f'重译所选 · {len(old)}' if old else '重译所选')
        self.translate_button.configure(text=f'翻译所选 · {len(rows)}' if rows else '翻译所选')
        self.update_actions()

    def update_actions(self):
        for button in self.controls:button.configure(state='disabled' if self.busy else 'normal')
        for entry,state in self.editables:entry.configure(state='disabled' if self.busy else state)
        self.sync_check.configure(state='disabled' if self.busy else 'normal')
        available=bool(self.scan) and not self.busy
        for button in (self.build_button,self.report_button,self.more_button):
            button.configure(state='normal' if available else 'disabled')
        self.select_button.configure(state='normal' if self.visible and not self.busy else 'disabled')
        self.clear_button.configure(state='normal' if self.checked and not self.busy else 'disabled')
        self.translate_button.configure(state='normal' if available and self.selected_entries() else 'disabled')
        self.retranslate_button.configure(state='normal' if available and self.selected_retranslations() else 'disabled')
        editable=bool(self.current) and not self.busy
        dirty=bool(self.current) and self.translation.get('1.0','end-1c')!=self.current.translation
        self.translation.configure(state='normal' if editable else 'disabled')
        self.save_button.configure(state='normal' if editable and dirty else 'disabled')
        self.revert_button.configure(state='normal' if editable and dirty else 'disabled')
        self.reference_button.configure(state='normal' if self.current and (self.current.refs or self.current.target) else 'disabled')
        self.dirty_var.set('未保存' if dirty else '')

    def toggle_checked(self,iid):
        if self.busy or iid not in self.visible:return
        entry=self.visible[iid]
        if entry.uid in self.checked:self.checked.remove(entry.uid)
        else:self.checked.add(entry.uid)
        self.tree.set(iid,'check','✓' if entry.uid in self.checked else '')
        self.update_selection_count()

    def on_tree_click(self,event):
        iid=self.tree.identify_row(event.y)
        if iid and self.tree.identify_column(event.x)=='#1':self.toggle_checked(iid)

    def toggle_focused(self,event=None):
        selection=self.tree.selection()
        if selection:self.toggle_checked(selection[0])
        return 'break'

    def select_visible(self):
        if self.busy:return
        for e in self.visible.values():
            if self.mode.get()=='已忽略' or e.status not in ('cached','ignored') or retranslation_eligible(e):self.checked.add(e.uid)
        self.refresh()

    def select_filtered(self):
        if self.busy:return
        for e in self.filtered:
            if self.mode.get()=='已忽略' or e.status not in ('cached','ignored') or retranslation_eligible(e):self.checked.add(e.uid)
        self.refresh()

    def clear_visible(self):
        if self.busy:return
        self.checked.clear();self.refresh()

    def ignore_checked(self):
        if self.busy or not self.scan:return
        for e in self.scan.entries:
            if e.uid in self.checked:self.cache.ignore(e)
        self.checked.clear();self.refresh();self.write_log('所选条目已忽略')

    def unignore_checked(self):
        if self.busy or not self.scan:return
        for e in self.scan.entries:
            if e.uid in self.checked and e.status=='ignored':self.cache.ignore(e,False)
        self.cache.load(self.scan.entries);align_translations(self.scan);self.checked.clear();self.refresh()
        self.write_log('所选条目已恢复')

    def set_text(self,widget,text,state=None):
        widget.configure(state='normal');widget.delete('1.0','end');widget.insert('1.0',text);widget.edit_modified(False)
        if state:widget.configure(state=state)

    def clear_detail(self):
        self._loading=True;self.current=None;self._editor_original=''
        self.detail_title.set('条目详情');self.detail_var.set('选择左侧条目')
        self.set_text(self.original,'','disabled');self.set_text(self.translation,'','disabled')
        self._loading=False

    def source_text(self):
        if not self.current:return ''
        entry=self.current;text=entry.source
        if self.showing_reference:
            if entry.target:text+='\n\n当前汉化\n'+entry.target
            for lang,value in entry.refs.items():text+='\n\n'+{'kr':'韩文','jp':'日文','en':'英文'}.get(lang,lang)+'参考\n'+value
        return text

    def toggle_reference(self):
        self.showing_reference=not self.showing_reference
        self.reference_button.configure(text='收起参考' if self.showing_reference else '参考语种')
        self.set_text(self.original,self.source_text(),'disabled')

    def show_entry(self,event=None):
        choice=self.tree.selection()
        if not choice or choice[0] not in self.visible:return
        entry=self.visible[choice[0]]
        self.remember_draft();self.current=entry;self._loading=True
        self.detail_title.set(entry.category+' · '+FIELD_LABELS.get(entry.field,'任务目标' if entry.field.startswith('goalDescription') else '文本'))
        note=entry.retranslation_error or entry.error or entry.consistency_note
        self.detail_var.set(pathlib.PurePosixPath(entry.file).name+(('\n'+note[:180]+('…' if len(note)>180 else '')) if note else ''))
        self.set_text(self.original,self.source_text(),'disabled')
        draft=self.drafts.get(entry)
        self.set_text(self.translation,entry.translation if draft is None else draft)
        self.translation.edit_reset();self._editor_original=entry.translation;self._loading=False;self.update_actions()

    def editor_changed(self,event=None):
        if not self.translation.edit_modified():return
        self.translation.edit_modified(False)
        if self._loading or self.busy or not self.current:return
        self.remember_draft();self.update_actions()

    def remember_draft(self):
        if self._loading or not self.current or not hasattr(self,'translation'):return
        text=self.translation.get('1.0','end-1c')
        if text!=self._editor_original:self.drafts.remember(self.current,text)
        elif self.drafts.get(self.current) is not None and text==self.current.translation:self.drafts.discard(self.current)
        if self._draft_after:self.root.after_cancel(self._draft_after)
        self._draft_after=self.root.after(700,self.flush_drafts)

    def flush_drafts(self):
        if self._draft_after:self.root.after_cancel(self._draft_after)
        self._draft_after=None
        try:self.drafts.save()
        except (BridgeError,OSError) as exc:self.write_log(str(exc),announce=False)

    def revert_draft(self):
        if self.busy or not self.current:return
        self.drafts.discard(self.current);self._loading=True
        self.set_text(self.translation,self.current.translation);self._editor_original=self.current.translation
        self._loading=False;self.flush_drafts();self.update_actions()

    def save_manual(self):
        if self.busy or not self.current:return
        try:
            entry=self.current;self.cache.put(entry,self.translation.get('1.0','end-1c'),'manual')
            align_translations(self.scan);self.drafts.discard(entry)
            self._loading=True;self.set_text(self.translation,entry.translation);self._editor_original=entry.translation
            self._loading=False;self.flush_drafts();self.refresh();self.write_log('译文已保存，生成语言包后生效')
        except BridgeError as exc:self.show_error(exc)

    def start_retranslate(self):
        self.start_translate(replacing=True)

    def start_translate(self,replacing=False):
        if self.busy or not self.scan:return
        if not self.match_scan_paths():return
        rows=self.selected_retranslations() if replacing else self.selected_entries()
        if not rows:self.write_log('请先勾选已有 AI 或手动译文' if replacing else '请先勾选待翻译的条目');return
        try:
            config,key=self.collect_settings();client=Client(config,key,self.stop,progress=self.emit)
            settings.save(self.directory,config,key)
        except BridgeError as exc:self.show_page('settings');self.show_error(exc);return
        self.config=config;self.api_key=key
        def work():
            from .core import assert_fresh
            assert_fresh(self.scan)
            fn=retranslate if replacing else translate
            return fn(rows,self.scan,self.cache,client,config,self.stop,self.emit)
        def done(stats):
            self.checked.difference_update(e.uid for e in rows if e.status=='cached' and not e.retranslation_error)
            self.refresh();self.write_log(f'{"重译" if replacing else "翻译"}完成 · 已保存 {stats["success"]} 条 · 失败 {stats["failed"]} 条'+('（保留旧译文）' if replacing and stats['failed'] else ''))
        self.run(work,done,'重译' if replacing else '翻译',None if replacing else rows)

    def start_build(self):
        if self.busy or not self.scan:return
        if not self.match_scan_paths():return
        self.run(lambda:install_pack(self.scan,self.directory,self.stop,self.emit),self.built,'生成语言包')

    def match_scan_paths(self,announce=True):
        game=pathlib.Path(self.game_var.get().strip()).absolute()
        base=pathlib.Path(self.api_vars['baseline_path'].get().strip() or game/'LimbusCompany_Data/Lang/LLC_zh-CN').absolute()
        if self.scan and game==self.scan.game and base==self.scan.baseline:return True
        if announce:self.write_log('目录已更改，请重新扫描')
        return False

    def built(self,result):
        self.watch_pending=False
        self.write_log(f'语言包已生成 · {result["ai_entries"]} 条补译 · 游戏中选择 {PACK_NAME}')

    def report(self):
        if self.busy or not self.scan:return
        def done(path):
            self.write_log(f'报告已保存：{path}')
            os.startfile(str(path))
        self.run(lambda:export_report(self.scan,self.directory),done,'导出报告')

    def test_api(self):
        if self.busy:return
        try:config,key=self.collect_settings();client=Client(config,key,self.stop,progress=self.emit)
        except BridgeError as exc:self.show_error(exc);return
        self.run(client.test,lambda text:(self.api_status.set(text),self.write_log(text)),'测试连接')

    def fetch_models(self):
        if self.busy:return
        try:
            config,key=self.collect_settings()
            if not config['model']:config['model']='placeholder'
            client=Client(config,key,self.stop,progress=self.emit)
        except BridgeError as exc:self.show_error(exc);return
        def done(models):
            self.model_combo.configure(values=models);self.api_status.set(f'已获取 {len(models)} 个模型')
            self.write_log(f'已获取 {len(models)} 个模型')
        self.run(client.models,done,'获取模型')

    def sync_pending(self):
        if self.busy or not self.scan or not self.watch_pending or not self.monitor_var.get():return
        if not self.match_scan_paths(announce=False):return
        def work():
            if game_running():return None
            return install_pack(self.scan,self.directory,self.stop,self.emit)
        def done(result):
            if result:self.built(result)
            else:self.write_log('等待游戏退出后同步语言包')
        self.run(work,done,'同步语言包')

    def watch(self):
        self.root.after(60000,self.watch)
        if self.busy or not self.monitor_var.get() or not self.scan:return
        if not self.match_scan_paths(announce=False):return
        if self.watch_pending:self.sync_pending();return
        def done(sig):
            if sig!=self.last_watch_signature:self.start_scan()
            else:self.status.set('就绪')
        self.run(lambda:signature(self.scan.game,self.scan.baseline,self.scan.source_lang),done,'检查更新')

    def on_close(self):
        self.remember_draft();self.flush_drafts()
        try:
            config,key=self.collect_settings();settings.save(self.directory,config,key)
        except Exception:pass
        if self.busy:
            self.closing=True;self.request_stop();self.write_log('正在保存结果，当前请求结束后关闭…')
        else:self.root.destroy()
