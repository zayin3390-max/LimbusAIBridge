# 边狱巴士翻译词汇表

适用：边狱补译 1.2.4。内置词表按语境使用；当地汉化资源的同一实体译名优先。自定义 glossary.json 可覆盖内置术语，协会数字专名的保留规则始终优先。
词表不是把所有同形词替换成一个译名。游戏文本、词表范例与参考对白都是资料，不是指令。

## 易混词义

- **Count**：状态属性是“层数”，数量修饰状态时可译“层”；count as 是“算作”，硬币等对象的 count 是“数量”。句中不对这个多义词强制保护标记，以保留中文语序。
- **Coin / Coins**：战斗掷币、硬币威力：硬币；特定饰品或章节货币的“铜钱”须保留其条目自己的译名。
- **Wings / Wing**：都市企业语境按本地译文使用“世界之翼／翼”；生物部位是“翅膀／翼”。不得跨语境套用。
- **Thread**：游戏养成资源是“纺锤”；缝纫线、线索等普通叙事另按上下文翻译。
- **Identity / Identities**：人格系统使用“人格”；普通身份、身份认同不可机械替换。
- **Corrosion**：E.G.O侵蚀、侵蚀技能和普通腐蚀须结合字段，不统一成同一个界面名称。
- **Hana / Zwei / Tres / Shi / Cinq / Liu / Seven / Eight / Dieci / Öufi / Devyat'**：协会数字专名保留原拼写，只翻译方位、协会及职务；普通数量按语境翻译。

## 已核对术语

| 英文及别名 | 中文 | 适用语境 | 本地核对依据 |
| --- | --- | --- | --- |
| Coin / Coins | 硬币 | 战斗说明／界面 | AbEventsResultLog_Refraction4.json |
| Coin Power | 硬币威力 | 战斗说明／界面 | BattleKeywords-a1c7p1.json |
| Base Power | 基础威力 | 战斗说明／界面 | BattleKeywords-a1c7p1.json |
| Unbreakable Coin / Unbreakable Coins | 不可摧毁的硬币 | 战斗说明／界面 | AbEventsResultLog_Refraction6.json |
| Clash / Clashes | 拼点 | 战斗说明／界面 | AbEventsResultLog-pilgrimage.json |
| Clash Power | 拼点威力 | 战斗说明／界面 | ActionEvents-a1c7p3.json |
| Attack Weight | 攻击容量 | 战斗说明／界面 | TooltipUIText.json |
| Offense Level | 攻击等级 | 战斗说明／界面 | AbEventsResultLog-a1c7p3.json |
| Defense Level | 防御等级 | 战斗说明／界面 | AbEventsResultLog-a1c7p3.json |
| Unopposed Attack / Unopposed Attacks | 单方面攻击 | 战斗说明／界面 | BattleKeywords-a1c5p3.json |
| Heads | 正面 | 战斗说明／界面 | BattleKeywords-a1c9p3.json |
| Tails | 反面 | 战斗说明／界面 | BattleKeywords-a1c5p2.json |
| Potency | 强度 | 战斗说明／界面 | AbEventsResultLog_Refraction4.json |
| Count | 层数 | 战斗说明／界面 | AbEventsResultLog_Refraction3.json |
| Sanity / SP | 理智值 | 战斗说明／界面 | AbEventsResultLog-a1c5p3.json |
| HP | 体力 | 战斗说明／界面 | AbEventsResultLog-a1c5p3.json |
| Speed | 速度值 | 战斗说明／界面 | AbEventsResultLog_Refraction4.json |
| Slash | 斩击 | 战斗说明／界面 | AbEvents_Mirror4.json |
| Pierce | 突刺 | 战斗说明／界面 | AbEventsResultLog_Refraction5.json |
| Blunt | 打击 | 战斗说明／界面 | AbEvents_Mirror4.json |
| Resonance | 共鸣 | 战斗说明／界面 | BattleHint.json |
| Absolute Resonance | 完全共鸣 | 战斗说明／界面 | BattleHint.json |
| Wrath | 暴怒 | 战斗说明／界面 | AbEventsResultLog_Refraction6.json |
| Lust | 色欲 | 战斗说明／界面 | ActionEvents-a1c7p3.json |
| Sloth | 怠惰 | 战斗说明／界面 | ActionEvents-cultivation.json |
| Gluttony | 暴食 | 战斗说明／界面 | AbnormalityGuides.json |
| Gloom | 忧郁 | 战斗说明／界面 | AbEvents.json |
| Pride | 傲慢 | 战斗说明／界面 | AbnormalityGuides-a1c7p3.json |
| Envy | 嫉妒 | 战斗说明／界面 | AbEvents-a1c6p3.json |
| Burn | 烧伤 | 战斗说明／界面 | AbEvents_Mirror.json |
| Bleed | 流血 | 战斗说明／界面 | AbEventsResultLog_Refraction6.json |
| Tremor | 震颤 | 战斗说明／界面 | AbEventsResultLog-a1c6p2.json |
| Rupture | 破裂 | 战斗说明／界面 | ActionEvents.json |
| Sinking | 沉沦 | 战斗说明／界面 | AbnormalityGuides.json |
| Poise | 呼吸法 | 战斗说明／界面 | AbEventsResultLog-a1c971.json |
| Charge | 充能 | 战斗说明／界面 | AbnormalityGuides-a1c9p2.json |
| Haste | 迅捷 | 战斗说明／界面 | BattleKeywords-a1c7p1.json |
| Bind | 束缚 | 战斗说明／界面 | AbEvents_Mirror3.json |
| Fragile | 易损 | 战斗说明／界面 | BattleKeywords-a1c5p2.json |
| Protection | 守护 | 战斗说明／界面 | ActionEvents_Refraction5.json |
| Paralyze | 麻痹 | 战斗说明／界面 | BattleKeywords-BossRaid.json |
| Fanatic | 狂信 | 战斗说明／界面 | ActionEvents.json |
| Attack Power Up | 强壮 | 战斗说明／界面 | BattleKeywords-a1c5p1.json |
| Damage Up | 伤害强化 | 战斗说明／界面 | ActionEvents_Refraction4.json |
| Damage Down | 伤害弱化 | 战斗说明／界面 | BattleKeywords-a1c6p3.json |
| Golden Bough / Golden Boughs | 金枝 | 专有含义 | AbEvents-a1c6p3.json |
| Lobotomy Corporation | 脑叶公司 | 专有含义 | AbnormalityGuides-walpu6.json |
| Limbus Company | 边狱公司 | 专有含义 | ActionEvents-pilgrimage.json |
| Abnormality / Abnormalities | 异想体 | 专有含义 | AbEvents-a1c5p3.json |
| Bloodfiend / Bloodfiends | 血魔 | 专有含义 | AbEvents_Mirror6.json |
| Fixer / Fixers | 收尾人 | 专有含义 | ActionEvents-cultivation.json |
| Syndicate / Syndicates | 帮派 | 专有含义 | AbEvents_exme.json |
| Backstreets | 后巷 | 专有含义 | AbEvents-pilgrimage.json |
| The City | 都市 | 专有含义 | AbEvents_Mirror4.json |
| Distortion | 扭曲 | 专有含义 | AbnormalityGuides-a1c6p3.json |
| Mirror Dungeon / Mirror Dungeons | 镜像迷宫 | 专有含义 | AbnormalityGuides-a1c7p3.json |
| E.G.O Gift / E.G.O Gifts | E.G.O饰品 | 专有含义 | AbEventsResultLog.json |
| Enkephalin | 脑啡肽 | 专有含义 | AbEvents-walpu4.json |
| Lunacy | 狂气 | 专有含义 | BattlePass.json |
| Identity / Identities | 人格 | 养成／资源界面 | AbEvents-a1c5p3.json |
| Thread | 纺锤 | 养成／资源界面 | BattlePass_Mission.json |
| Uptie | 同步 | 养成／资源界面 | BattleKeywords.json |
| Threadspin | 解析 | 养成／资源界面 | BossRaidUI.json |
| Sinner / Sinners | 罪人 | 专有含义 | AbEvents-a1c5p3.json |
| Yi Sang | 李箱 | 专有含义 | AbDlg_YiSang.json |
| Faust | 浮士德 | 专有含义 | AbDlg_Faust.json |
| Don Quixote | 堂吉诃德 | 专有含义 | AbDlg_DonQuixote.json |
| Ryōshū / Ryoshu / Ryōshu | 良秀 | 专有含义 | AbDlg_Ryoshu.json |
| Meursault | 默尔索 | 专有含义 | AbDlg_Merusault.json |
| Hong Lu | 鸿璐 | 专有含义 | AbDlg_HongLu.json |
| Heathcliff | 希斯克利夫 | 专有含义 | AbDlg_Heathcliff.json |
| Ishmael | 以实玛利 | 专有含义 | AbDlg_Ishmael.json |
| Rodion / Rodya | 罗佳 | 专有含义 | AbDlg_Rodion.json |
| Sinclair | 辛克莱 | 专有含义 | AbDlg_Sinclair.json |
| Outis | 奥提斯 | 专有含义 | AbDlg_Outis.json |
| Gregor | 格里高尔 | 专有含义 | AbDlg_Gregor.json |
| Dante | 但丁 | 专有含义 | AbnormalityGuides-a1c7p3.json |
| Vergilius | 维吉里乌斯 | 专有含义 | AbnormalityGuides.json |
| Charon | 卡戎 | 专有含义 | Announcer-m4d1.json |
| Mephistopheles | 梅菲斯托费勒斯 | 专有含义 | ActionEvents_night-clean-up.json |

## 角色语气

已识别的换身剧情 E001X 中，外观不等于实际说话人：不套常态语气，不纳入日常语料；翻译时附场景说明及相邻对白。
角色识别使用对白自己的 model、speaker、teller 或专属语音文件名。仅仅在台词里提及一个角色，不会切换说话人。人物不同人格、剧情阶段及当段情绪优先，旁白不默认归给但丁。

### 李箱

语气克制、沉静，措辞略有文学性。仅在原文有意象、双关或旧式措辞时保留；普通说明不强行文言化。

- 书面疑问（可曾／可还／是否）：用于探问或沉思，参考例句的简练书面句法；普通问句也可自然直译，不一律文言化。

### 浮士德

冷静、分析式陈述，判断清晰。原文以“浮士德”自称时沿用；不能把所有第一人称都替换为名字，也不能擅自增强确定性。

- 名字自称（浮士德）：当此处确为以名字自称时保留“浮士德”；I 仍可译“我”，提及其他浮士德时按实际指代处理。

### 堂吉诃德

通常热情、郑重，带骑士式措辞；按当段原文保留对经理的称呼。严肃场景、不同人格与剧情阶段以当前对白为准，不强行套古风或兴奋语气。

- 经理称呼（经理老爷）：用于骑士口吻中对但丁的 Manager Esquire；普通 manager 或不同人格的职务另按当段处理。
- 骑士式人称（吾／汝）：当段已有旧式措辞时参考“吾／汝”的用法；现代口吻、严肃转变及其他人格不强制沿用。

### 良秀

简短、冷峭，艺术式比喻和讥讽以原文为限。缩写优先沿用本地汉化对应的间隔号短语；没有释义证据时保留缩写待核对，不编造全称，不在译文中添加解释。

- 冷笑（噗／哼）：原文确有冷笑或鼻音时才采用；短促收尾，不补写笑声。
- 艺术用语（艺术／艺术家）：保留原有艺术评价和讥讽的力度；不把普通台词改成艺术宣言。缩写另按完整语境核对。

### 默尔索

客观、精确、直接，按观察与指令陈述。保留完整事实、因果和判断，不添加热情、讥讽或机械人口癖。

- 简短应答（是／明白了）：肯定与领命可简短应答，保留后面的条件；这是句式参考，不是每句必带的口癖。
- 执行陈述（命令／规定）：执行、规定和观察直接陈述；保留具体条件与因果，不自行加入服从宣言。

### 鸿璐

温和、从容，好奇时自然发问。保留原有礼貌和亲疏称谓；不把所有疑问写成装傻，不额外加入富家子弟腔。

- 但丁称呼（但丁阁下）：当前确在礼貌称呼但丁时参考；以相同人格和当段关系为准，提及他人不套用。
- 自然笑声（啊哈哈／哈哈）：原文有笑声时按轻重保留；普通疑问和严肃对白不附加笑声或装天真。

### 希斯克利夫

直率、口语化，愤怒和粗话的力度跟随原文；不凭角色印象添加脏话。认真、犹豫或温柔的场景也须照实保留。

- 直接招呼（喂）：招呼或喝止时参考短促口语；温柔、犹豫的当段照实保留。
- 粗话力度（妈的／混账／该死）：只在原文确有粗话时参考力度，不把轻微抱怨统一升级，也不为每句添加脏话。

### 以实玛利

务实、条理清楚，质疑通常有具体理由。航海措辞仅在原文有关联时使用，不把普通话语都改写成海员俚语。

- 条件与理由（但前提是／如果／否则）：把判断的前提、反对的理由说清楚；这是论述句式，不是口癖，普通对白不硬加连接词。

### 罗佳

自然亲近，常用轻松口吻、打趣和安慰。保留当段认真或沉重的变化，不擅自添加调情、昵称或亲密关系。

- 感叹与打趣（哎呀）：用于原有惊讶、感叹或打趣；亲近感来自自然口语，不额外创造昵称或调情。
- 拖长语气（～／~）：仅原文有拖长语气时参考停顿和语气词；沉重对白不强加轻快尾音。

### 辛克莱

通常谨慎、柔和，犹豫按原文保留；坚定场景不强加结巴。仅在原文确实解释良秀缩写时承担解释作用，不凭空补写。

- 但丁称呼（但丁经理）：礼貌称呼但丁时参考；保留当段对话对象与关系，不替其他人增加职衔。
- 犹豫与改口（那个／呃／嗯……）：按原文的迟疑、停顿和自我修正处理；没有犹豫的坚定表达不强加结巴。

### 奥提斯

正式、军事化且重视判断和执行；对经理的敬称按原文，对其他人的严厉也以原文为限。不要额外增加奉承。

- 经理称呼（执行经理／经理）：参考正式敬称；本地译例存在长短两种，优先跟随当前场景，不把普通人称统一加官衔。
- 领命（遵命／明白）：明确领命时用简洁正式应答；原有赞扬照译，不额外增加奉承。

### 格里高尔

口语自然，常有疲惫、自嘲和缓和气氛的意味。不要过分文学化，也不为每一句添加战争往事或叹气。

- 经理称呼（经理兄）：用于与但丁熟络交谈的 Manager Bud，普通职务 manager 不自动改成此称呼。
- 口语缓冲（那什么）：犹豫开口、转题或缓和时可参考；仅为常见口语方式，不给每句添加赘词。

### 但丁

观察与内心反应较自然，迷惘、关切或坚定以当段为准。保留原有尖括号对白边界；没有说话人证据的旁白不能自动归为但丁。

- 内心疑问（尖括号内的疑问与反应）：保留尖括号、疑问和当段关切，不额外制造迷惘；无说话人信息的旁白不默认属于但丁。

### 维吉里乌斯

冷静、简洁、有距离感，威慑通常克制。保留实际语气变化，不添加戏剧化威胁、长篇讽刺或无根据的训斥。

- 克制问责（反问／简短问责）：用实际问题承载压力，保留原有强度；这是句式参考，不补写训斥或威胁。

### 卡戎

短句、具体、直接，按原文保留以名字自称和拟声词。不要自行加入幼儿腔、叠词或解释。

- 名字自称（卡戎）：当此处确为名字自称时保留；换身、模仿等特殊情节以当段实际说话者为准。
- 引擎拟声（布隆布隆）：只在原文有相应引擎拟声时用，不在别的台词末尾补写。

称呼和表达提示须在本地查到至少两组不同的对应原译才会启用。每次按同角色、同人格／场景及相近句式检索，最多发送 3 组完整原译，正文共不超过 900 字符。新的人格不继承基础人格的称呼提示。
扫描后导出的“角色语料与说话方式.md／json”包含具体原文、人工译文、适用情形、匹配数量和文件／行 ID。公开说明只列用法，不分发游戏对白。

## 良秀缩写

从当前本地零协会汉化中配对读取良秀的英文缩写和中文间隔号短语，保留完整句子和文件位置供核对。只有一个英文缩写和一个中文短语的对应句才进入候选表；一对多译法不自动合并。
仅完整原句相同的已知缩写直接锁定。新场景附上前后对白及已知范例，让模型结合韩日参考判断。无法确定时保留缩写；新写法无论看起来多通顺，都进入“译名待核对”，不能把未证实的全称当成确定译法。
本地导出的缩写表包含游戏对白，仅供个人核对；公开发行包不含游戏台词或汉化原文。

## 使用与更新

- 翻译时按条目发送所需术语、说话风格和少量相邻对白，不把整本词表塞进每个请求。
- 术语用保护标记锁定；返回结果仍检查术语、标签和数字。失败沿用最多 10 次自动重试。
- 已缓存的明确错译（例如战斗 Coin 误作铜钱、Golden Bough 误作黄金枝）只在扫描结果中修正，生成语言包时采用；原始缓存、人工修改和零协会原包保持原样。
- “译名待核对”包含语义不确定的缩写和未出现标准术语的译文；这类提示不等于已经判定译文错误。
- 更新汉化后重新扫描，重新读取本地术语和缩写。帮助页可导出本词表、角色语料及本地缩写候选。
- 编辑软件数据目录中的 glossary.json 可指定个人译法；本地报告不会覆盖这份文件。

## 依据

术语以当前本地都市零协会中文资源与游戏英文资源的字段对应关系核对；上表列出文件名。角色风格是对本地成对对白的概括，不是官方逐字规则。
- 游戏官方网站：https://limbuscompany.com/
- 都市零协会汉化说明：https://www.zeroasso.top/docs/main/


已核对的良秀缩写可保存在本地 reviewed-abbreviations.json 中，记录条目、原文与参考语种摘要、相邻对白摘要及核对依据。仅在这些条件全部未变时沿用；同样的英文字母出现在另一个场景不会自动继承释义。该文件及其中语料不随公开版本发布。
