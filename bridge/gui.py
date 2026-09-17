from __future__ import annotations
import json
import os
import pathlib
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from . import VERSION
from . import settings
from .core import (BridgeError, Cancelled, Cache, scan_game, signature, install_pack,
                   export_report, game_running, detect_game, PACK_NAME, MARKER, PACK_RULES_VERSION, atomic_write)
from .provider import Client, translate, include_dependencies
from .consistency import align_translations

CATEGORIES=('人格','E.G.O','主线剧情','敌方','卡池','关联术语','其他')
REASONS={'missing':'缺失','empty':'空值待确认','placeholder':'待译标记','foreign':'韩文待核对','mixed':'混合语言待核对','same':'原文保留待核对','metadata':'剧情附加字段'}
STATES={'pending':'待译','cached':'已有补译','ignored':'已忽略','failed':'校验/请求失败'}
HELP='''使用顺序

1. 先让 Steam 和游戏完成本次更新，再退出游戏。
2. 用原来的 LLC 工具箱更新零协会汉化（若已有更新）。
3. 打开本工具，在「API 设置」填写自己的 Chat Completions 兼容地址、API Key、模型名。
4. 「扫描更新」后选择分类。默认只勾选首次扫描以后新增、且仍缺少译文的人格、E.G.O、主线剧情、敌方和卡池条目。
5. 点击「翻译勾选项」。这一步才会发送所选游戏文本到你配置的 API，并消耗服务商额度。
6. 检查译文后点击「生成独立语言包」。此操作不调用 API。
7. 在游戏启动页的自定义语言按钮中选择 LimbusAI_zh-CN，按游戏提示重启。基础语言推荐英文。

零协会更新后

本工具以本地 LLC_zh-CN 为基准。窗口保持打开时，每 60 秒检查一次本地文件；有变化且游戏已退出时自动重建独立包。新到的零协会译文优先，原有 AI 缓存保留备用。没有自动付费翻译，也不会自动下载零协会更新。
关闭软件后不监控；下次打开会同步。若从原工具箱启动游戏，它可能把选定语言切回 LLC_zh-CN，此时在游戏启动页重新选择 LimbusAI_zh-CN。

如何识别新内容

按 ID、技能等级和硬币位置对齐；同一资源组中，总表已经汉化的相同 ID、相同原文不会再次报缺。首次扫描建立当前原文基线，不把存量差异称为新版本漏译。默认「更新待补译」只推荐此后新增/变更且缺少译文的字段；无更新时应为 0。首次使用时若更新已经发生，或要核对旧文本，可手动切到「全部差异（需核对）」查看。
原文保留、空值、剧情省略字段、旧文件等只表示文件差异，不证明当前游戏画面缺译。하나协会等专名保留；中文夹杂外语也不作为自动重译依据。明确开发备注和有译文覆盖的重复导出文件会排除，依据写入扫描报告。无法安全对齐的重复 ID 保留原状。

协会数字专名

Hana、Zwei、Tres、Shi、Cinq、Liu、Devyat'、Dieci、Öufi 等按原文拼写保留；纯专名不会列为待译，整句翻译时也会保护其拼写。Seven/Eight 在明确的协会语境或单独名称中保留，普通数量照常翻译。Association/Assoc.、方位、科室与职务照常汉化。零协会已有的一协、二协等译文继续保留。

文件保护

官方入口：LimbusCompany_Data/Lang/自定义语言名。原版游戏文件、LLC_zh-CN、LLC 工具箱和原 config.json 均只读取。本工具只创建/维护自己的 LimbusAI_zh-CN 目录；若遇到同名非本工具目录，或你手动修改了生成包，立即停止覆盖。每次变更保留上一份受影响文件于 data/history；不用的自有旧文件移到 data/retired。回到原汉化只需在游戏里选 LLC_zh-CN。

翻译范围与质量

人格：名字、主动/被动技能、背景剧情和语音文本。E.G.O：名称、觉醒/侵蚀技能、被动及语音。敌方：名字、技能、被动与观察记录。另含主线文本与卡池说明。本工具只处理官方导出的文本 JSON，不识别图片里的文字，不改图像或游戏逻辑。
引擎关键词、富文本、变量、换行及数字会校验；不通过的条目不会进入生成包。校验只能保证部分格式和数字，不能保证语义正确，尤其应核对技能条件。AI 会参考本机的韩文/日文和零协会已有术语。

自动重试

网络中断、超时、限流和服务器临时故障会自动等待后重试，默认最多 10 次（不含首次请求）。等待逐步增加，通常不超过 60 秒；服务返回更长等待时间时遵照其提示。日志显示重试进度，可随时点击“停止”取消等待。
达到上限后，当前批次标为失败，继续处理后面的批次；不会把失败批次拆开以绕过重试上限。已成功条目立即保存，下次重试不会重复发送。密钥失效、额度/付款错误或接口设置错误需要人工修正，会提示并结束本轮。保护标记、数字、中文正文和 JSON 格式校验失败也会自动纠正重试；只重发失败条目，成功项先保存。网络失败与校验失败共用每条最多 10 次重试额度，不会各重试 10 次。长输出/批次格式失败会缩小批次，拆分前已用次数仍然保留。失败原因会写入 validation-failures.jsonl 供核对，不保存密钥和被拒绝的完整响应。
可在 API 设置修改重试次数（0–10），0 表示关闭自动重试。

跨界面译名一致

扫描、翻译结束、生成语言包时统一检查：状态栏与弹窗，技能各等级，技能/被动正文引用，人格、E.G.O、敌人名称，剧情说话人、称谓和地点，章节及卡池中的术语。相同资源按实体 ID、字段和原文对应；跨 ID 的名称还需本地韩文/日文等对应证据，不把不同实体仅凭同英文强行合并。
零协会已有译名优先；缺失处再使用个人术语、手动审校和已有 AI 定名。已知名称会在 API 请求中锁定。若本次勾选了尚未翻译、且会被正文引用的名称，先翻译名称，再按原有并行数处理正文；不会擅自发送未勾选条目。
普通对白、同词异义、不同数值与硬币描述分别保留；Hana、Zwei 等协会数字专名的规则不变。正文中已识别的别译在原文确实提及对应术语时修正。无法确定的新别译列入「译名需核对」，可查看原文、参考语种并手动审校；导出扫描报告会附上「译名一致性.md」及「译名对齐清单.csv」。
原汉化不改写，原始缓存记录保留；在内存和生成的独立包中统一。完整人工名称优先于较短名称片段。此功能检查可识别的术语关系，不代替全文语义审校。
升级后，退出游戏、关闭旧工具窗口，重新打开新版并点击「生成独立语言包」即可应用现有译文修复，无需重新付费翻译。开启自动同步时，新版也会在游戏退出后按新规则同步。


加速翻译

API 设置新增「并行批次数」：默认 2，可设 1–4。2 表示同时处理两批；接口允许时可改为 4，设为 1 恢复逐批模式。已有成功译文继续复用；不同批次各自处理，某批纠错时其他批次可继续。
校验纠错仅等待 1 秒；断网、超时及服务器故障仍使用原来的逐步退避，最多 10 次重试的共同上限不变。并行请求收到限流或服务端等待指示时，会暂停所有通道的新请求。已发出的请求可能仍在返回，停止后会保留其中通过校验的译文，再结束本轮。
保持每批 12–20 条通常便于控制输出长度；频繁出现“输出达到长度上限”时可调小到 6–10。并行数越高不保证越快，具体取决于服务商限额、模型速度和重试情况。没有更换模型或关闭质量校验。

API 与隐私

支持标准 /chat/completions 接口（包含 OpenAI 兼容的中转、DeepSeek、部分本地服务）。不直接支持 /responses、Anthropic /messages 或 Gemini 原生接口；这些服务需使用兼容网关。模型名可以手填或获取列表。JSON 模式默认关闭，减少服务商兼容性问题。
密钥默认只保留在当前进程；勾选「加密记住」后用当前 Windows 用户的 DPAPI 加密保存。不会在日志、报告或请求错误里写出密钥。仅选定条目的原文、附近角色信息、参考语种及相关零协会术语发给你填写的服务商。不会读取其它软件的 API Key。
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

class App:
    def __init__(self, root, directory, *, autostart=True):
        self.root=root; self.directory=pathlib.Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True)
        self.cache=Cache(self.directory)
        self.config,self.api_key=settings.load(self.directory)
        self.scan=None; self.checked=set(); self.visible={}; self.current=None
        self.events=queue.Queue(); self.stop=threading.Event(); self.busy=False; self.worker=None
        self.closing=False; self.watch_pending=False; self.last_watch_signature=''
        root.title(f'边狱补译 · Limbus AI Bridge {VERSION}')
        width=min(1240,root.winfo_screenwidth()-80); height=min(900,root.winfo_screenheight()-100)
        root.geometry(f'{width}x{height}'); root.minsize(min(980,width),min(720,height))
        root.configure(bg='#f2f4f7')
        style=ttk.Style(root); style.theme_use('clam')
        style.configure('.',font=('Microsoft YaHei UI',10),background='#f2f4f7')
        style.configure('TButton',padding=(12,7))
        style.configure('Primary.TButton',background='#29554b',foreground='white')
        style.map('Primary.TButton',background=[('active','#346e61'),('disabled','#aab8b3')])
        style.configure('Treeview',rowheight=27,background='white',fieldbackground='white',font=('Microsoft YaHei UI',9))
        style.configure('Treeview.Heading',font=('Microsoft YaHei UI',9,'bold'),padding=6)
        style.configure('TNotebook.Tab',padding=(18,8))
        header=tk.Frame(root,bg='#202b30',height=80); header.pack(fill='x')
        tk.Label(header,text='边狱补译',font=('Microsoft YaHei UI',22,'bold'),fg='#f4f4ee',bg='#202b30').pack(side='left',padx=24,pady=16)
        tk.Label(header,text='零协会译文优先  ·  只补未汉化的内容',font=('Microsoft YaHei UI',11),fg='#ccd8d6',bg='#202b30').pack(side='left',padx=8)
        notebook=ttk.Notebook(root); notebook.pack(fill='both',expand=True,padx=16,pady=12)
        workspace=ttk.Frame(notebook,padding=12); api=ttk.Frame(notebook,padding=20); help_tab=ttk.Frame(notebook,padding=16)
        notebook.add(workspace,text='补译工作台'); notebook.add(api,text='API 设置'); notebook.add(help_tab,text='使用说明')
        self.build_work(workspace); self.build_settings(api)
        help_text=tk.Text(help_tab,wrap='word',font=('Microsoft YaHei UI',11),padx=14,pady=12,bg='white',relief='flat')
        help_scroll=ttk.Scrollbar(help_tab,command=help_text.yview); help_text.configure(yscrollcommand=help_scroll.set)
        help_scroll.pack(side='right',fill='y'); help_text.pack(fill='both',expand=True); help_text.insert('1.0',HELP); help_text.configure(state='disabled')
        self.status=tk.StringVar(value='准备就绪。扫描和生成语言包均不调用 API。')
        ttk.Label(root,textvariable=self.status,anchor='w').pack(fill='x',padx=24,pady=(0,8))
        self.root.protocol('WM_DELETE_WINDOW',self.on_close)
        self.root.after(100,self.poll)
        if autostart:
            self.root.after(450,self.start_scan)
            self.root.after(60000,self.watch)

    def build_work(self, frame):
        row=ttk.Frame(frame); row.pack(fill='x')
        ttk.Label(row,text='游戏目录').pack(side='left')
        self.game_var=tk.StringVar(value=self.config['game_path'])
        ttk.Entry(row,textvariable=self.game_var).pack(side='left',fill='x',expand=True,padx=8)
        self.controls=[]
        self.button(row,'浏览',self.choose_game)
        self.button(row,'扫描更新',self.start_scan,primary=True)
        self.summary_var=tk.StringVar(value='首次扫描建立当前版本基线；默认只推荐此后新增的待补译内容。')
        ttk.Label(frame,textvariable=self.summary_var,font=('Microsoft YaHei UI',11,'bold')).pack(anchor='w',pady=(12,10))
        filters=ttk.Frame(frame); filters.pack(fill='x')
        self.category_vars={}
        for category in CATEGORIES:
            var=tk.BooleanVar(value=category!='其他'); self.category_vars[category]=var
            ttk.Checkbutton(filters,text=category,variable=var,command=self.refresh).pack(side='left',padx=(0,12))
        self.mode=tk.StringVar(value='更新待补译')
        combo=ttk.Combobox(filters,textvariable=self.mode,values=['更新待补译','全部差异（需核对）','已有补译','译名需核对'],state='readonly',width=17)
        combo.pack(side='left',padx=8); combo.bind('<<ComboboxSelected>>',lambda e:self.refresh())
        self.search=tk.StringVar(); ttk.Entry(filters,textvariable=self.search,width=20).pack(side='right')
        ttk.Label(filters,text='搜索文件 / 原文').pack(side='right',padx=8)
        self.search.trace_add('write',lambda *_:self.refresh())
        actions=ttk.Frame(frame); actions.pack(fill='x',pady=8)
        self.button(actions,'勾选当前列表',self.select_visible)
        self.button(actions,'取消当前勾选',self.clear_visible)
        self.button(actions,'忽略勾选',self.ignore_checked)
        self.button(actions,'恢复勾选项',self.unignore_checked)
        self.selected_var=tk.StringVar(); ttk.Label(actions,textvariable=self.selected_var).pack(side='right',padx=8)
        pane=ttk.Panedwindow(frame,orient='horizontal'); pane.pack(fill='both',expand=True)
        left=ttk.Frame(pane); right=ttk.Frame(pane,padding=(12,0,0,0)); pane.add(left,weight=6); pane.add(right,weight=5)
        self.tree=ttk.Treeview(left,columns=('check','category','file','reason','state'),show='headings',selectmode='browse')
        for key,text,width,stretch in [('check','选',36,False),('category','分类',65,False),('file','文件 / 字段',270,True),('reason','原因',95,False),('state','状态',95,False)]:
            self.tree.heading(key,text=text); self.tree.column(key,width=width,minwidth=width if not stretch else 100,stretch=stretch)
        scroll=ttk.Scrollbar(left,orient='vertical',command=self.tree.yview); self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y'); self.tree.pack(fill='both',expand=True)
        self.tree.bind('<Button-1>',self.on_tree_click); self.tree.bind('<<TreeviewSelect>>',self.show_entry)
        self.detail_var=tk.StringVar(value='选择一条查看原文和译文')
        ttk.Label(right,textvariable=self.detail_var,wraplength=470).pack(anchor='w',pady=(0,4))
        self.original=tk.Text(right,height=8,wrap='word',font=('Microsoft YaHei UI',10),relief='flat',padx=8,pady=6)
        self.original.pack(fill='both',expand=True)
        ttk.Label(right,text='补译 / 手动修订（保存时校验标签和数字）').pack(anchor='w',pady=(8,4))
        self.translation=tk.Text(right,height=8,wrap='word',font=('Microsoft YaHei UI',10),relief='flat',padx=8,pady=6)
        self.translation.pack(fill='both',expand=True)
        self.button(right,'保存此条译文',self.save_manual)
        foot=ttk.Frame(frame); foot.pack(fill='x',pady=(10,4))
        self.button(foot,'翻译勾选项',self.start_translate,primary=True)
        self.button(foot,'生成独立语言包',self.start_build,primary=True)
        self.button(foot,'导出扫描报告',self.report)
        self.stop_button=ttk.Button(foot,text='停止',command=self.stop.set,state='disabled'); self.stop_button.pack(side='left',padx=4)
        self.monitor_var=tk.BooleanVar(value=self.config.get('monitor',True))
        ttk.Checkbutton(foot,text='开启期间同步零协会更新',variable=self.monitor_var).pack(side='right')
        self.log=tk.Text(frame,height=4,wrap='word',font=('Microsoft YaHei UI',9),relief='flat',padx=8,pady=6,bg='#e7ecec',state='disabled')
        self.log.pack(fill='x',pady=(6,0))

    def button(self,parent,text,command,primary=False):
        b=ttk.Button(parent,text=text,command=command,style='Primary.TButton' if primary else 'TButton')
        b.pack(side='left',padx=(0,6),pady=2); self.controls.append(b); return b

    def build_settings(self,frame):
        ttk.Label(frame,text='接入你自己的翻译 API',font=('Microsoft YaHei UI',17,'bold')).grid(row=0,column=0,columnspan=3,sticky='w',pady=(0,12))
        ttk.Label(frame,text='填写 Chat Completions 兼容服务。只有点击连接测试或翻译时才会调用。',wraplength=780).grid(row=1,column=0,columnspan=3,sticky='w',pady=(0,18))
        self.api_vars={}
        fields=[('api_base','API 地址','https://你的服务商/v1 或完整 /chat/completions 地址'),('model','模型名称','输入服务商提供的模型 ID'),('baseline_path','零协会目录','留空自动使用游戏目录下的 Lang/LLC_zh-CN'),('timeout','超时（秒）','10–300'),('batch_size','每批条目','默认 12；长剧情会按文本长度自动拆分'),('concurrency','并行批次数','1–4；默认 2，同时翻译多个批次'),('max_tokens','输出长度上限','默认 8192；服务商不兼容时可调低'),('retries','最大重试次数','0–10；默认 10，不含首次请求')]
        row=2
        for key,label,hint in fields:
            var=tk.StringVar(value=str(self.config.get(key,''))); self.api_vars[key]=var
            ttk.Label(frame,text=label).grid(row=row,column=0,sticky='w',pady=5,padx=(0,18))
            if key=='model':
                self.model_combo=ttk.Combobox(frame,textvariable=var); entry=self.model_combo
            else: entry=ttk.Entry(frame,textvariable=var)
            entry.grid(row=row,column=1,sticky='ew',pady=5)
            ttk.Label(frame,text=hint,foreground='#667378',wraplength=310).grid(row=row,column=2,sticky='w',padx=14)
            row+=1
        self.key_var=tk.StringVar(value=self.api_key)
        ttk.Label(frame,text='API Key').grid(row=row,column=0,sticky='w',pady=8)
        ttk.Entry(frame,textvariable=self.key_var,show='●').grid(row=row,column=1,sticky='ew',pady=8)
        ttk.Label(frame,text='远程服务必填；localhost 本地模型可留空',foreground='#667378').grid(row=row,column=2,sticky='w',padx=14); row+=1
        self.remember_var=tk.BooleanVar(value=self.config.get('remember_key',False))
        ttk.Checkbutton(frame,text='用 Windows 当前用户加密记住密钥',variable=self.remember_var).grid(row=row,column=1,sticky='w',pady=8); row+=1
        self.json_var=tk.BooleanVar(value=self.config.get('json_mode',False))
        ttk.Checkbutton(frame,text='启用 response_format JSON 模式（仅兼容服务）',variable=self.json_var).grid(row=row,column=1,sticky='w',pady=8); row+=1
        buttons=ttk.Frame(frame); buttons.grid(row=row,column=0,columnspan=3,sticky='w',pady=18)
        self.button(buttons,'保存设置',self.save_settings,primary=True)
        self.button(buttons,'测试连接（少量 tokens）',self.test_api)
        self.button(buttons,'获取模型列表',self.fetch_models)
        self.api_status=tk.StringVar(value='密钥不会写入日志。默认不持久保存。')
        row+=1; ttk.Label(frame,textvariable=self.api_status,wraplength=900).grid(row=row,column=0,columnspan=3,sticky='w',pady=8)
        frame.columnconfigure(1,weight=1)

    def collect_settings(self):
        config=dict(self.config)
        config.update({k:v.get().strip() for k,v in self.api_vars.items()})
        for key in ('timeout','batch_size','max_tokens','retries','concurrency'):
            try: config[key]=int(config[key])
            except ValueError: raise BridgeError(f'{key} 必须是整数')
        if not 0 <= config['retries'] <= 10:
            raise BridgeError('最大重试次数必须在 0–10 之间')
        if not 1 <= config['concurrency'] <= 4:
            raise BridgeError('并行批次数必须在 1–4 之间')
        config.update(game_path=self.game_var.get().strip(),remember_key=self.remember_var.get(),json_mode=self.json_var.get(),monitor=self.monitor_var.get())
        return config,self.key_var.get().strip()

    def save_settings(self):
        try:
            self.config,self.api_key=self.collect_settings(); settings.save(self.directory,self.config,self.api_key)
            self.api_status.set('设置已保存；密钥已加密。' if self.config['remember_key'] else '设置已保存；密钥仅在本次窗口中使用。')
        except Exception as exc: self.show_error(exc)

    def choose_game(self):
        p=filedialog.askdirectory(title='选择包含 LimbusCompany.exe 的文件夹',initialdir=self.game_var.get() or None)
        if p: self.game_var.set(p)

    def emit(self,text): self.events.put(('log',str(text)))

    def write_log(self,text):
        key=self.key_var.get() if hasattr(self,'key_var') else self.api_key
        if key: text=text.replace(key,'[密钥已隐藏]')
        self.status.set(text)
        line=f'[{time.strftime("%H:%M:%S")}] {text}\n'
        self.log.configure(state='normal'); self.log.insert('end',line); self.log.see('end'); self.log.configure(state='disabled')
        try:
            with (self.directory/'activity.log').open('a',encoding='utf-8') as f: f.write(line)
        except OSError: pass

    def show_error(self,exc):
        text=str(exc)
        key=self.key_var.get() if hasattr(self,'key_var') else self.api_key
        if key: text=text.replace(key,'[密钥已隐藏]')
        self.write_log(text); self.api_status.set(text)
        if not self.closing: messagebox.showerror('未完成此操作',text,parent=self.root)

    def run(self,fn,callback):
        if self.busy: return
        self.busy=True; self.stop.clear()
        for b in self.controls: b.configure(state='disabled')
        self.stop_button.configure(state='normal')
        def task():
            try: self.events.put(('done',(callback,fn())))
            except Cancelled as exc: self.events.put(('cancel',str(exc)))
            except Exception as exc: self.events.put(('error',exc))
        self.worker=threading.Thread(target=task,daemon=True); self.worker.start()

    def poll(self):
        try:
            while True:
                kind,data=self.events.get_nowait()
                if kind=='log': self.write_log(data); continue
                self.busy=False
                for b in self.controls: b.configure(state='normal')
                self.stop_button.configure(state='disabled')
                if kind=='done':
                    callback,result=data; callback(result)
                elif kind=='cancel': self.write_log(data); self.refresh()
                elif kind=='error': self.show_error(data); self.refresh()
                if self.closing: self.root.destroy(); return
        except queue.Empty: pass
        self.root.after(100,self.poll)

    def start_scan(self):
        if self.busy: return
        try: config,key=self.collect_settings()
        except BridgeError as exc: self.show_error(exc); return
        if not config['game_path']:
            self.write_log('未自动找到游戏，请浏览选择游戏根目录。'); return
        self.config=config; self.api_key=key
        def work():
            scan=scan_game(config['game_path'],config['baseline_path'] or None,config['source_lang'],self.cache,self.stop,self.emit)
            self.cache.observe(scan)
            return scan
        self.run(work,self.scanned)

    def scanned(self,scan):
        self.scan=scan; self.last_watch_signature=scan.signature
        self.checked={e.uid for e in scan.entries if e.recommended and e.category!='其他' and e.status not in ('cached','ignored')}
        self.refresh()
        self.write_log(f'扫描完成。零协会版本 {scan.version}；当前分类的更新待补译 {len(self.checked)} 条。存量差异不代表本次更新或游戏内漏译。')
        if scan.status_alignment_changes:
            self.write_log(f'已统一同一状态的 {len({r["uid"] for r in scan.status_alignment_changes})} 个字段；生成语言包后生效。')
        if any(r.get('needs_review',True) for r in scan.status_alignment_conflicts):
            self.write_log(f'有 {sum(r.get("needs_review",True) for r in scan.status_alignment_conflicts)} 组状态译文需人工核对，详见导出报告；原有汉化保持原样。')
        if scan.consistency_changes:
            self.write_log(f'已统一技能等级、名称及正文引用中的 {len({r["uid"] for r in scan.consistency_changes})} 个字段。')
        if scan.consistency_conflicts:
            self.write_log(f'有 {len(scan.consistency_conflicts)} 处术语需核对，详见“导出扫描报告”内的译名一致性报告。')
        for message in scan.warnings: self.write_log('扫描提示：'+message)
        marker=scan.game/'LimbusCompany_Data/Lang'/PACK_NAME/MARKER
        if self.monitor_var.get() and marker.exists():
            try:
                metadata=json.loads(marker.read_text(encoding='utf-8'))
                if metadata.get('source_signature')!=scan.signature or metadata.get('pack_rules_version',0)!=PACK_RULES_VERSION:
                    self.watch_pending=True
                    self.root.after(250,self.sync_pending)
            except (ValueError,OSError): pass

    def matches(self,e):
        if not self.category_vars[e.category].get(): return False
        mode=self.mode.get()
        if mode=='更新待补译' and not e.recommended: return False
        if mode=='已有补译' and e.status!='cached': return False
        if mode=='译名需核对' and not e.consistency_note:return False
        search=self.search.get().strip().casefold()
        return not search or search in (e.file+' '+e.source+' '+(e.target or '')+' '+e.translation).casefold()

    def refresh(self):
        if not self.scan: return
        self.tree.delete(*self.tree.get_children()); self.visible={}
        for i,e in enumerate(self.scan.entries):
            if not self.matches(e): continue
            iid=str(i); self.visible[iid]=e
            self.tree.insert('', 'end',iid=iid,values=('✓' if e.uid in self.checked else '',e.category,e.file+' · '+e.field,('存量差异待核对' if e.candidate and not e.newly_seen else REASONS.get(e.reason,e.reason)),STATES.get(e.status,e.status)))
        s=self.scan.summary(); self.summary_var.set(f'零协会 {s["version"]}  ·  更新待补译 {s["recommended"]} 项  ·  可复用补译 {s["cached"]} 项  ·  当前列表 {len(self.visible)} 项')
        self.update_selection_count()

    def update_selection_count(self):
        selected=[e for e in self.visible.values() if e.uid in self.checked and e.status not in ('cached','ignored')]
        selected=[e for e in include_dependencies(selected,self.scan) if e.status not in ('cached','ignored')]
        self.selected_var.set(f'当前待翻译勾选 {len(selected)} 条 / 原文 {sum(len(e.source) for e in selected):,} 字符')

    def on_tree_click(self,event):
        iid=self.tree.identify_row(event.y)
        if iid and self.tree.identify_column(event.x)=='#1' and not self.busy:
            e=self.visible[iid]
            if e.uid in self.checked: self.checked.remove(e.uid)
            else: self.checked.add(e.uid)
            self.tree.set(iid,'check','✓' if e.uid in self.checked else ''); self.update_selection_count()

    def select_visible(self):
        for e in self.visible.values():
            if e.status not in ('cached','ignored'): self.checked.add(e.uid)
        self.refresh()

    def clear_visible(self):
        for e in self.visible.values(): self.checked.discard(e.uid)
        self.refresh()

    def ignore_checked(self):
        for e in self.visible.values():
            if e.uid in self.checked: self.cache.ignore(e); self.checked.discard(e.uid)
        self.refresh()

    def unignore_checked(self):
        for e in self.visible.values():
            if e.uid in self.checked and e.status=='ignored': self.cache.ignore(e,False)
        self.cache.load(self.scan.entries); align_translations(self.scan); self.refresh()

    def show_entry(self,_=None):
        selection=self.tree.selection()
        if not selection or selection[0] not in self.visible: return
        e=self.visible[selection[0]]; self.current=e
        self.detail_var.set(f'{e.file}\n{e.path}\n{e.consistency_note or e.error or REASONS.get(e.reason,e.reason)}')
        text='【原文】\n'+e.source
        if e.target: text+='\n\n【当前语言包】\n'+e.target
        for lang,ref in e.refs.items(): text+='\n\n【'+lang.upper()+' 参考】\n'+ref
        self.original.configure(state='normal'); self.original.delete('1.0','end'); self.original.insert('1.0',text); self.original.configure(state='disabled')
        self.translation.delete('1.0','end'); self.translation.insert('1.0',e.translation)

    def save_manual(self):
        if not self.current: return
        try:
            self.cache.put(self.current,self.translation.get('1.0','end-1c'),'manual')
            align_translations(self.scan)
            self.write_log('此条译文已校验并保存。生成语言包后生效。'); self.refresh()
        except BridgeError as exc: self.show_error(exc)

    def start_translate(self):
        if not self.scan: self.write_log('请先扫描。'); return
        if not self.match_scan_paths(): return
        selected=[e for e in self.visible.values() if e.uid in self.checked and e.status not in ('cached','ignored')]
        selected=[e for e in include_dependencies(selected,self.scan) if e.status not in ('cached','ignored')]
        if not selected: self.write_log('当前列表没有勾选的待翻译条目。'); return
        try:
            config,key=self.collect_settings(); settings.save(self.directory,config,key)
            client=Client(config,key,self.stop,progress=self.emit)
        except BridgeError as exc: self.show_error(exc); return
        self.config=config; self.api_key=key
        def work():
            from .core import assert_fresh
            assert_fresh(self.scan)
            return translate(selected,self.scan,self.cache,client,config,self.stop,self.emit)
        def done(stats):
            self.refresh(); self.write_log(f'翻译结束：已保存 {stats["success"]} 条，未通过 {stats["failed"]} 条。请审阅后生成独立语言包。')
        self.run(work,done)

    def start_build(self):
        if not self.scan: self.write_log('请先扫描。'); return
        if not self.match_scan_paths(): return
        self.run(lambda:install_pack(self.scan,self.directory,self.stop,self.emit),self.built)

    def match_scan_paths(self):
        game=pathlib.Path(self.game_var.get().strip()).absolute()
        base=pathlib.Path(self.api_vars['baseline_path'].get().strip() or game/'LimbusCompany_Data/Lang/LLC_zh-CN').absolute()
        if self.scan and game==self.scan.game and base==self.scan.baseline: return True
        self.write_log('游戏或零协会目录已更改，请先重新扫描。'); return False

    def built(self,result):
        self.watch_pending=False
        self.write_log(f'独立包已生成：{result["ai_entries"]} 条补译。游戏启动页选择 {PACK_NAME}，原文件保持不变。')

    def report(self):
        if not self.scan: return
        self.run(lambda:export_report(self.scan,self.directory),lambda p:self.write_log(f'报告已保存：{p}'))

    def test_api(self):
        try:
            config,key=self.collect_settings(); client=Client(config,key,self.stop,progress=self.emit)
        except BridgeError as exc: self.show_error(exc); return
        self.run(client.test,lambda text:(self.api_status.set(text),self.write_log(text)))

    def fetch_models(self):
        try:
            config,key=self.collect_settings()
            if not config['model']: config['model']='placeholder'
            client=Client(config,key,self.stop,progress=self.emit)
        except BridgeError as exc: self.show_error(exc); return
        def done(models):
            self.model_combo.configure(values=models); self.api_status.set(f'已获取 {len(models)} 个模型，请从下拉框选择。')
        self.run(client.models,done)

    def sync_pending(self):
        if self.busy or not self.scan or not self.watch_pending: return
        def work():
            if game_running(): return None
            return install_pack(self.scan,self.directory,self.stop,self.emit)
        def done(result):
            if result: self.built(result)
            else: self.write_log('检测到本地更新；待游戏退出后同步独立语言包。')
        self.run(work,done)

    def watch(self):
        self.root.after(60000,self.watch)
        if self.busy or not self.monitor_var.get() or not self.scan: return
        if not self.match_scan_paths(): return
        if self.watch_pending: self.sync_pending(); return
        def work(): return signature(self.scan.game,self.scan.baseline,self.scan.source_lang)
        def done(sig):
            if sig!=self.last_watch_signature:
                self.write_log('检测到游戏/零协会文件变化，正在重新扫描；不会自动调用 API。')
                self.start_scan()
        self.run(work,done)

    def on_close(self):
        try:
            config,key=self.collect_settings(); settings.save(self.directory,config,key)
        except Exception: pass
        if self.busy:
            self.closing=True; self.stop.set(); self.write_log('正在停止并保存结果，当前请求返回后关闭…')
        else: self.root.destroy()
